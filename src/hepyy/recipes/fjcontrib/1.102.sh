set -e
fjconfig={{ fastjet_prefix }}/bin/fastjet-config
if [ ! -x "$fjconfig" ]; then
  echo "[fjcontrib] ERROR: fastjet-config not found at $fjconfig"
  echo "[fjcontrib] Install fastjet first: heyy install fastjet"
  exit 1
fi
fjlibs=$($fjconfig --libs --plugins)
# Pass 1: static build — configure reads 'version' files first
./configure --fastjet-config=$fjconfig --prefix={{ prefix }} LDFLAGS="$fjlibs"
# Hide 'version' files after configure: macOS clang's C++20 <version> lookup
# picks up these plain-text files and fails with "expected unqualified-id"
find . -maxdepth 2 -name 'version' -type f | while read vf; do mv "$vf" "$vf.bak"; done
make -j{{ n_cores }} all && make install
# Restore for pass 2 configure (it re-reads version files)
find . -maxdepth 2 -name 'version.bak' -type f | while read vf; do mv "$vf" "$(echo $vf | sed 's/\.bak$//')"; done
# Pass 2: PIC rebuild + per-contrib shared libraries
make distclean || true
./configure --fastjet-config=$fjconfig --prefix={{ prefix }} CXXFLAGS='-fPIC' LDFLAGS="$fjlibs"
find . -maxdepth 2 -name 'version' -type f | while read vf; do mv "$vf" "$vf.bak"; done
make -j{{ n_cores }} all && make install
mkdir -p {{ prefix }}/lib
set +e
failed_libs=""
for cdir in */; do
  c=$(basename "$cdir")
  [ -d "$c" ] || continue
  cd "$c"
  ofiles=$(ls *.o 2>/dev/null)
  if [ -n "$ofiles" ]; then
    if [ "Darwin" == $(uname) ]; then
      # -undefined dynamic_lookup defers cross-contrib symbol resolution to load time
      {{ CXX }} -fPIC -dynamiclib -undefined dynamic_lookup \
        -o {{ prefix }}/lib/lib$c.dylib *.o $fjlibs \
        || failed_libs="$failed_libs $c"
    else
      {{ CXX }} -fPIC -shared \
        -o {{ prefix }}/lib/lib$c.so *.o $fjlibs -L{{ prefix }}/lib \
        || failed_libs="$failed_libs $c"
    fi
  fi
  cd {{ srcdir }}
done
if [ -n "$failed_libs" ]; then
  echo "[fjcontrib] WARNING: shared libs not built (cross-contrib deps missing?):$failed_libs"
  echo "[fjcontrib] Static libs from 'make install' are still available."
fi

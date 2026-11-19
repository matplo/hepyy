set -e
# The hepforge release tarball bundles all contribs — no SVN needed.

fjconfig={{ fastjet_prefix }}/bin/fastjet-config
if [ ! -x "$fjconfig" ]; then
  echo "[fjcontrib] ERROR: fastjet-config not found at $fjconfig"
  echo "[fjcontrib] Install fastjet first: heyy install fastjet"
  exit 1
fi
fjlibs=$($fjconfig --libs --plugins)

# Clean any stale state before configuring
make distclean 2>/dev/null || true

# --- Pass 1: static build ---
# Hide plain-text 'version' files before configure: macOS clang's C++20
# <version> header lookup picks them up and fails with "expected unqualified-id"
./configure --fastjet-config=$fjconfig --prefix={{ prefix }} LDFLAGS="$fjlibs"
find . -maxdepth 2 -name 'version' -type f | while read vf; do mv "$vf" "$vf.bak"; done
make -j{{ n_cores }} all && make install
# Restore 'version' files — pass 2 configure re-reads them
find . -maxdepth 2 -name 'version.bak' -type f | while read vf; do mv "$vf" "$(echo $vf | sed 's/\.bak$//')"; done

# --- Pass 2: PIC rebuild + per-contrib shared libraries ---
make distclean || true
./configure --fastjet-config=$fjconfig --prefix={{ prefix }} CXXFLAGS='-fPIC' LDFLAGS="$fjlibs"
find . -maxdepth 2 -name 'version' -type f | while read vf; do mv "$vf" "$vf.bak"; done
make -j{{ n_cores }} all && make install

mkdir -p {{ prefix }}/lib

# Use 'configure --list' to get the authoritative contrib list (avoids
# processing scripts/ and other non-contrib directories).
contribs=$(./configure --list 2>/dev/null || true)

if [ -z "$contribs" ]; then
  echo "[fjcontrib] WARNING: ./configure --list returned nothing; falling back to directory scan"
  contribs=$(for d in */; do [ -d "$d" ] && basename "$d"; done)
fi

if [ "Darwin" == $(uname) ]; then
  soext=dylib
  soflags="-fPIC -dynamiclib -undefined dynamic_lookup"
else
  soext=so
  soflags="-fPIC -shared"
fi

set +e
failed_libs=""
for c in $contribs; do
  [ -d "$c" ] || continue
  cd "$c"
  # Drop example object files — they don't belong in the shared lib
  rm -f *example*.o 2>/dev/null
  ofiles=$(ls *.o 2>/dev/null)
  if [ -n "$ofiles" ]; then
    shlib={{ prefix }}/lib/lib${c}.${soext}
    # shellcheck disable=SC2086
    {{ CXX }} $soflags -o "$shlib" *.o $fjlibs \
      && echo "[fjcontrib] shared lib: lib${c}.${soext}" \
      || { echo "[fjcontrib] WARNING: could not build lib${c}.${soext}"; failed_libs="$failed_libs $c"; }
  fi
  cd {{ srcdir }}
done
set -e

if [ -n "$failed_libs" ]; then
  echo "[fjcontrib] WARNING: shared libs not built (cross-contrib deps?):$failed_libs"
  echo "[fjcontrib] Static libs from 'make install' are still available."
fi

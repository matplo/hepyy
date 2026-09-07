set -e
lhapdf_prefix="{{ lhapdf_prefix }}"
if [ -z "$lhapdf_prefix" ]; then
  echo "[jewel] ERROR: lhapdf not found in hepyy registry — install lhapdf first"
  exit 1
fi
make LHAPDF_PATH="$lhapdf_prefix/lib"
mkdir -p {{ prefix }}/bin {{ prefix }}/settings {{ prefix }}/info
cp jewel-{{ version }}-* {{ prefix }}/bin/
cp *.dat {{ prefix }}/settings/
for f in *.txt README GUIDELINES; do [ -f "$f" ] && cp "$f" {{ prefix }}/info/ || true; done

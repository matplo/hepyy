set -e
if command -v swig >/dev/null 2>&1; then
  echo "[lhapdf] swig $(swig -version 2>&1 | awk '/Version/{print $3}') found — building with Python bindings"
  python_flag="--with-python-sys-prefix"
else
  echo "[lhapdf] swig not found — building without Python bindings"
  python_flag="--without-python"
fi
./configure --prefix={{ prefix }} --enable-shared $python_flag
make -j{{ n_cores }}
make install

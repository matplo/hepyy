set -e
opts=""
# Optional packages: flags are added only when already installed in hepyy
[ -n "{{ fastjet_prefix }}" ] && opts="$opts --with-fastjet3={{ fastjet_prefix }}" && echo "[pythia8] FastJet : {{ fastjet_prefix }}"
[ -n "{{ hepmc3_prefix }}"  ] && opts="$opts --with-hepmc3={{ hepmc3_prefix }}"   && echo "[pythia8] HepMC3  : {{ hepmc3_prefix }}"
[ -n "{{ lhapdf_prefix }}"  ] && opts="$opts --with-lhapdf6={{ lhapdf_prefix }}"  && echo "[pythia8] LHAPDF6 : {{ lhapdf_prefix }}"
echo "[pythia8] configure: $opts"
./configure --prefix={{ prefix }} $opts
make -j{{ n_cores }}
make install

"""
Demo: Pythia8 event generation + FastJet anti-kt jets → ROOT file.

Generates pp → QCD dijet events, clusters jets with anti-kt R=0.4, and
writes per-jet variables into a ROOT TTree using uproot — no ROOT C++
required, so pip-cppyy (pythia8/fastjet) and ROOT file I/O coexist cleanly.

Run with:
    python demo_pythia_fastjet_root.py

Output: pythia_jets.root  (TTree "jets" with per-jet branches)
Read back with ROOT or uproot:
    root -l pythia_jets.root
    jets->Draw("pt>>h(50,0,200)","is_leading==1")

    import uproot
    with uproot.open("pythia_jets.root") as f:
        pt = f["jets"]["pt"].array()
"""

# Packages must be loaded before running. Either:
#   module load fastjet pythia8   # autoload hook handles the rest
# or uncomment:
#   import hepyy; hepyy.load("fastjet"); hepyy.load("pythia8")
import cppyy
import pythia8
import fastjet
import uproot
import numpy as np

PseudoJetVec = cppyy.gbl.std.vector[fastjet.PseudoJet]

# ---------------------------------------------------------------------------
# Initialise Pythia: pp 13 TeV QCD dijets, pThat > 20 GeV
# ---------------------------------------------------------------------------
pythia = pythia8.Pythia()
pythia.readString("Beams:eCM = 13000.")
pythia.readString("HardQCD:all = on")
pythia.readString("PhaseSpace:pTHatMin = 20.")
pythia.readString("Next:numberShowEvent = 0")
pythia.readString("Print:quiet = on")
pythia.init()

# ---------------------------------------------------------------------------
# Jet definition: anti-kt R=0.4, pt > 20 GeV
# ---------------------------------------------------------------------------
R       = 0.4
pt_min  = 20.0
jet_def = fastjet.JetDefinition(fastjet.antikt_algorithm, R)

# ---------------------------------------------------------------------------
# Event loop — collect per-jet data into flat lists
# ---------------------------------------------------------------------------
n_events = 200

all_event      = []
all_pt         = []
all_eta        = []
all_phi        = []
all_e          = []
all_m          = []
all_nconst     = []
all_is_leading = []

print(f"Generating {n_events} Pythia8 pp → dijets events, anti-kt R={R}, pt > {pt_min} GeV")

for i_event in range(n_events):
    if not pythia.next():
        continue

    event = pythia.event

    particles = PseudoJetVec()
    for i in range(event.size()):
        p = event[i]
        if not p.isFinal() or not p.isVisible():
            continue
        particles.push_back(fastjet.PseudoJet(p.px(), p.py(), p.pz(), p.e()))

    if particles.size() == 0:
        continue

    cs   = fastjet.ClusterSequence(particles, jet_def)
    jets = fastjet.sorted_by_pt(cs.inclusive_jets(pt_min))

    for j, jet in enumerate(jets):
        all_event.append(i_event)
        all_pt.append(jet.pt())
        all_eta.append(jet.eta())
        all_phi.append(jet.phi())
        all_e.append(jet.e())
        all_m.append(jet.m())
        all_nconst.append(len(cs.constituents(jet)))
        all_is_leading.append(1 if j == 0 else 0)

    if i_event < 3 and jets:
        print(f"  event {i_event}: {int(particles.size())} particles, {len(jets)} jets")
        for j, jet in enumerate(jets):
            print(f"    jet {j}: pt={jet.pt():.1f}  eta={jet.eta():.2f}  phi={jet.phi():.2f}  nconst={all_nconst[-(len(jets)-j)]}")

pythia.stat()

# ---------------------------------------------------------------------------
# Write ROOT file with uproot
# ---------------------------------------------------------------------------
outfile = "pythia_jets.root"
with uproot.recreate(outfile) as f:
    f["jets"] = {
        "event":      np.array(all_event,      np.int32),
        "pt":         np.array(all_pt,         np.float32),
        "eta":        np.array(all_eta,        np.float32),
        "phi":        np.array(all_phi,        np.float32),
        "e":          np.array(all_e,          np.float32),
        "m":          np.array(all_m,          np.float32),
        "nconst":     np.array(all_nconst,     np.int32),
        "is_leading": np.array(all_is_leading, np.int32),
    }

n_jets = len(all_pt)
print(f"\nWrote {outfile}  ({n_events} events, {n_jets} jets total)")
print("Branches: event, pt, eta, phi, e, m, nconst, is_leading")
print("\nQuick check:")
print("  root -l pythia_jets.root")
print('  jets->Draw("pt>>h(50,0,200)","is_leading==1")')

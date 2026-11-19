"""
Demo: Pythia8, FastJet and ROOT TTree using ROOT's shared cppyy runtime.

ROOT initializes its cppyy/cling runtime first; FastJet and Pythia then use
that same interpreter. Requires ROOT separately from the pip hepbundle, either
installed through hepyy or importable from the active system/conda environment.

Run in an environment with ROOT and the native packages installed:
    python demo_pythia_fastjet_root_cppyy.py
"""

# Establish ROOT's runtime before loading the other native libraries.
import importlib.util
import hepyy

if importlib.util.find_spec("ROOT") is None:
    hepyy.load("root")  # Expose a ROOT installation managed by hepyy.
import ROOT

hepyy.load(["fastjet", "pythia8"])

import cppyy
import pythia8
import fastjet

PseudoJetVec = cppyy.gbl.std.vector[fastjet.PseudoJet]

# ---------------------------------------------------------------------------
# ROOT output: TFile + TTree with scalar branches per jet
# ---------------------------------------------------------------------------
outfile = ROOT.TFile("pythia_jets_cppyy.root", "RECREATE")
tree    = ROOT.TTree("jets", "anti-kt R=0.4 jets from Pythia8 pp dijets")

import array
b_event      = array.array('i', [0])
b_pt         = array.array('f', [0.])
b_eta        = array.array('f', [0.])
b_phi        = array.array('f', [0.])
b_e          = array.array('f', [0.])
b_m          = array.array('f', [0.])
b_nconst     = array.array('i', [0])
b_is_leading = array.array('i', [0])

tree.Branch("event",      b_event,      "event/I")
tree.Branch("pt",         b_pt,         "pt/F")
tree.Branch("eta",        b_eta,        "eta/F")
tree.Branch("phi",        b_phi,        "phi/F")
tree.Branch("e",          b_e,          "e/F")
tree.Branch("m",          b_m,          "m/F")
tree.Branch("nconst",     b_nconst,     "nconst/I")
tree.Branch("is_leading", b_is_leading, "is_leading/I")

# ---------------------------------------------------------------------------
# Pythia: pp 13 TeV QCD dijets
# ---------------------------------------------------------------------------
pythia = pythia8.Pythia()
pythia.readString("Beams:eCM = 13000.")
pythia.readString("HardQCD:all = on")
pythia.readString("PhaseSpace:pTHatMin = 20.")
pythia.readString("Next:numberShowEvent = 0")
pythia.readString("Print:quiet = on")
pythia.init()

R       = 0.4
pt_min  = 20.0
jet_def = fastjet.JetDefinition(fastjet.antikt_algorithm, R)

# ---------------------------------------------------------------------------
# Event loop
# ---------------------------------------------------------------------------
n_events = 200
print(f"Generating {n_events} events, anti-kt R={R}, pt > {pt_min} GeV")

for i_event in range(n_events):
    if not pythia.next():
        continue

    event     = pythia.event
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
        b_event[0]      = i_event
        b_pt[0]         = jet.pt()
        b_eta[0]        = jet.eta()
        b_phi[0]        = jet.phi()
        b_e[0]          = jet.e()
        b_m[0]          = jet.m()
        b_nconst[0]     = len(cs.constituents(jet))
        b_is_leading[0] = 1 if j == 0 else 0
        tree.Fill()

    if i_event < 3 and jets:
        print(f"  event {i_event}: {int(particles.size())} particles, {len(jets)} jets, leading pt={jets[0].pt():.1f}")

pythia.stat()

n_entries = tree.GetEntries()
outfile.Write()
outfile.Close()

print(f"\nWrote pythia_jets_cppyy.root  ({n_events} events, {n_entries} jet entries)")
print('  root -l pythia_jets_cppyy.root')
print('  jets->Draw("pt>>h(50,0,200)","is_leading==1")')

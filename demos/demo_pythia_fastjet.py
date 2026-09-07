"""
Demo: Pythia8 event generation + FastJet anti-kt jet finding via hepyy.

Run with:
    python demo_pythia_fastjet.py
"""

# Packages must be loaded before running. Either:
#   module load fastjet pythia8   # autoload hook handles the rest
# or uncomment:
#   import hepyy; hepyy.load("fastjet"); hepyy.load("pythia8")
import cppyy
import pythia8
import fastjet

PseudoJetVec = cppyy.gbl.std.vector[fastjet.PseudoJet]

# ---------------------------------------------------------------------------
# Initialise Pythia
# ---------------------------------------------------------------------------
pythia = pythia8.Pythia()

# pp collisions at 13 TeV, QCD dijets with pThat > 20 GeV
pythia.readString("Beams:eCM = 13000.")
pythia.readString("HardQCD:all = on")
pythia.readString("PhaseSpace:pTHatMin = 20.")
pythia.readString("Next:numberShowEvent = 0")   # suppress per-event printout
pythia.readString("Print:quiet = on")

pythia.init()

# ---------------------------------------------------------------------------
# Jet definition: anti-kt R=0.4
# ---------------------------------------------------------------------------
R = 0.4
jet_def = fastjet.JetDefinition(fastjet.antikt_algorithm, R)
pt_min  = 20.0   # GeV — minimum jet pT to report

# ---------------------------------------------------------------------------
# Event loop
# ---------------------------------------------------------------------------
n_events    = 100
n_jets_total = 0
leading_pts  = []

print(f"Generating {n_events} Pythia8 pp → dijets events, clustering with anti-kt R={R}\n")

for i_event in range(n_events):
    if not pythia.next():
        continue

    event = pythia.event

    # Collect final-state visible particles into a std::vector<PseudoJet>
    particles = PseudoJetVec()
    for i in range(event.size()):
        p = event[i]
        if not p.isFinal():
            continue
        if not p.isVisible():   # skip neutrinos, LSP, etc.
            continue
        particles.push_back(fastjet.PseudoJet(p.px(), p.py(), p.pz(), p.e()))

    if particles.size() == 0:
        continue

    # Cluster
    cs   = fastjet.ClusterSequence(particles, jet_def)
    jets = fastjet.sorted_by_pt(cs.inclusive_jets(pt_min))

    n_jets_total += len(jets)

    if jets:
        leading_pts.append(jets[0].pt())

    # Print first 3 events in detail
    if i_event < 3 and jets:
        print(f"Event {i_event+1}:  {len(particles)} particles → {len(jets)} jets (pt > {pt_min} GeV)")
        for j, jet in enumerate(jets):
            nc = len(cs.constituents(jet))
            print(f"  jet {j}: pt={jet.pt():.1f}  eta={jet.eta():.2f}  phi={jet.phi():.2f}  n_const={nc}")
        print()

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
pythia.stat()

print(f"\n{'='*50}")
print(f"Processed {n_events} events")
print(f"Total jets found (pt > {pt_min} GeV): {n_jets_total}")
print(f"Mean jets per event: {n_jets_total / n_events:.2f}")

if leading_pts:
    avg_lead = sum(leading_pts) / len(leading_pts)
    max_lead = max(leading_pts)
    print(f"Leading jet <pT>:   {avg_lead:.1f} GeV")
    print(f"Leading jet max pT: {max_lead:.1f} GeV")

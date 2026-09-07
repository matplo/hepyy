"""
Demo: using FastJet via hepyy.

Run with:
    python demo_fastjet.py

Or, with the shell module system:
    eval "$(hepyy shell-init)"
    module load fastjet
    python demo_fastjet.py
"""

# Packages must be loaded before running. Either:
#   module load fastjet          # autoload hook handles the rest
# or uncomment:
#   import hepyy; hepyy.load("fastjet")
import cppyy
import fastjet

print(f"FastJet version: {fastjet.fastjet_version_string()}")
print()

# --- Build a simple event: a few particles as PseudoJets ---
# cppyy requires std::vector<PseudoJet>, not a plain Python list
PseudoJetVec = cppyy.gbl.std.vector[fastjet.PseudoJet]
particles = PseudoJetVec()
for px, py, pz, E in [
    ( 1.0,  0.5,  5.0, 6.0),
    (-0.5,  1.0,  3.0, 3.5),
    ( 0.8, -0.3, 10.0, 10.1),
    ( 0.2,  0.9,  2.0, 2.3),
    (-1.0, -0.5,  4.0, 4.4),
    ( 0.3, -1.2,  1.0, 1.7),
]:
    particles.push_back(fastjet.PseudoJet(px, py, pz, E))

# --- Cluster with anti-kt R=0.4 ---
R = 0.4
jet_def = fastjet.JetDefinition(fastjet.antikt_algorithm, R)
print(f"Jet definition: {jet_def.description()}")

cs = fastjet.ClusterSequence(particles, jet_def)
jets = fastjet.sorted_by_pt(cs.inclusive_jets(ptmin=1.0))

print(f"\nFound {len(jets)} jets with pt > 1 GeV:\n")
print(f"  {'#':<4} {'pt':>8} {'eta':>8} {'phi':>8} {'n_const':>8}")
print("  " + "-" * 44)
for i, jet in enumerate(jets):
    constituents = cs.constituents(jet)
    print(
        f"  {i:<4} {jet.pt():>8.3f} {jet.eta():>8.3f} "
        f"{jet.phi():>8.3f} {len(constituents):>8}"
    )

# --- Also try kt algorithm for comparison ---
print()
jet_def_kt = fastjet.JetDefinition(fastjet.kt_algorithm, R)
cs_kt = fastjet.ClusterSequence(particles, jet_def_kt)
jets_kt = fastjet.sorted_by_pt(cs_kt.inclusive_jets(ptmin=1.0))
print(f"kt R={R}: found {len(jets_kt)} jets")

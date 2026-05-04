# Real-World Test Data

Files used as regression test fixtures for edge cases in real research.

## 1SVC.pdb
- RCSB PDB entry 1SVC: NF-κB p50 homodimer / DNA complex
- Tests: DNA chain detection, altLoc handling, multi-chain protein
- Chains: A+B (protein), P (DNA, 19 nt), X (waters)

## Ailanthone.sdf
- PubChem CID 73188: Ailanthone (C20H24O7), quassinoid natural product
- Tests: SDF file ingestion with 3D coordinates, n_atoms=27, n_rotatable=3

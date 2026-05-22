"""Command-line entry point for Stage-1 end-to-end testing.

Usage:
    python -m dockmeow.core.cli \\
        --receptor examples/1AKE_with_ATP.pdb \\
        --ligand-smiles "CC(=O)OC1=CC=CC=C1C(=O)O" \\
        --output result/

    python -m dockmeow.core.cli \\
        --receptor examples/4DFR_methotrexate.pdb \\
        --ligand-file path/to/ligand.sdf \\
        --output result/

No PySide6 imports permitted in this module.
"""

from __future__ import annotations

import argparse
import datetime
import sys
from pathlib import Path


def build_parser() -> argparse.ArgumentParser:
    """Build and return the ArgumentParser for the CLI."""
    p = argparse.ArgumentParser(
        prog="python -m dockmeow.core.cli",
        description="DockMeow / 一键对接 — Stage 1 CLI (no GUI)",
    )
    p.add_argument("--receptor", required=True, type=Path, metavar="PDB",
                   help="Input receptor PDB file")
    p.add_argument("--ligand-smiles", metavar="SMILES",
                   help="Ligand as SMILES string")
    p.add_argument("--ligand-file", type=Path, metavar="FILE",
                   help="Ligand as SDF/MOL2/MOL file")
    p.add_argument("--output", required=True, type=Path, metavar="DIR",
                   help="Output directory")
    p.add_argument("--exhaustiveness", type=int, default=16, metavar="N",
                   help="Vina exhaustiveness (default 16)")
    p.add_argument("--num-modes", type=int, default=9, metavar="N",
                   help="Number of docking poses (default 9)")
    p.add_argument("--ph", type=float, default=7.4, metavar="PH",
                   help="pH for protonation (default 7.4)")
    p.add_argument("--seed", type=int, default=42, metavar="SEED",
                   help="Random seed (default 42)")
    p.add_argument("--no-report", action="store_true",
                   help="Skip PDF report generation")
    return p


def _progress(stage: str, pct: int, msg: str) -> None:
    print(f"  [{pct:3d}%] {stage}: {msg}", flush=True)


def main(argv: list[str] | None = None) -> int:
    """CLI entry point.

    Args:
        argv: Argument list (defaults to sys.argv[1:]).

    Returns:
        Exit code (0 = success, 1 = error).
    """
    from dockmeow.utils.logging_setup import setup_logging
    setup_logging()

    parser = build_parser()
    args = parser.parse_args(argv)

    if not args.ligand_smiles and not args.ligand_file:
        parser.error("one of --ligand-smiles or --ligand-file is required")

    output_dir: Path = args.output
    output_dir.mkdir(parents=True, exist_ok=True)

    work_dir = output_dir / "work"
    work_dir.mkdir(exist_ok=True)

    from dockmeow.core.docking import DockingConfig, run_docking
    from dockmeow.core.exceptions import DockMeowError
    from dockmeow.core.ligand import prepare_ligand_from_file, prepare_ligand_from_smiles
    from dockmeow.core.pocket import detect_pockets
    from dockmeow.core.receptor import prepare_receptor
    from dockmeow.core.report import ReportData, generate_pdf_report
    from dockmeow.core.results import export_poses_pdb, split_poses_to_sdf

    print(f"\n{'='*60}")
    print("  DockMeow / 一键对接 — Stage 1 CLI")
    print(f"{'='*60}\n")

    try:
        # --- Receptor ---
        print("▶ 准备受体…")
        receptor_work = work_dir / "receptor"
        receptor = prepare_receptor(
            args.receptor,
            receptor_work,
            progress_callback=_progress,
        )
        print(f"  ✓ 受体：{receptor.n_residues} 个残基，链 {receptor.chains}\n")

        if receptor.hetero_groups:
            ligands = [h for h in receptor.hetero_groups if h.is_likely_ligand]
            print(f"  检测到 HETATM 组（共结晶配体候选：{[h.resname for h in ligands]}）\n")

        # --- Ligand ---
        print("▶ 准备配体…")
        ligand_work = work_dir / "ligand"
        if args.ligand_smiles:
            ligand = prepare_ligand_from_smiles(
                args.ligand_smiles,
                name="ligand",
                work_dir=ligand_work,
                ph=args.ph,
                progress_callback=_progress,
            )
        else:
            ligand = prepare_ligand_from_file(
                args.ligand_file,
                work_dir=ligand_work,
                ph=args.ph,
                progress_callback=_progress,
            )
        print(f"  ✓ 配体：{ligand.n_atoms} 个重原子，{ligand.n_rotatable} 个可旋转键\n")

        # --- Pocket ---
        print("▶ 检测结合口袋…")
        pockets = detect_pockets(receptor, original_pdb=args.receptor)
        selected = pockets[0]
        print(f"  ✓ 使用口袋：{selected.label}（来源：{selected.source}）")
        print(f"  中心：{selected.center}  大小：{selected.size}\n")

        # --- Docking ---
        print("▶ 执行分子对接…")
        docking_work = work_dir / "docking"
        docking_work.mkdir(exist_ok=True)

        # Copy ligand pdbqt to docking work dir
        import shutil
        lig_in_work = docking_work / ligand.pdbqt_path.name
        shutil.copy2(ligand.pdbqt_path, lig_in_work)

        config = DockingConfig(
            receptor_pdbqt=receptor.pdbqt_path,
            ligand_pdbqt=lig_in_work,
            center=selected.center,
            size=selected.size,
            pocket_source=selected.source,
            exhaustiveness=args.exhaustiveness,
            num_modes=args.num_modes,
            seed=args.seed,
        )

        result = run_docking(config, progress_callback=_progress)
        print(f"\n  ✓ 最佳结合能：{result.scores[0]:.2f} kcal/mol")
        print(f"  耗时：{result.runtime_seconds:.1f} 秒\n")

        # --- Export ---
        print("▶ 导出结果…")
        import shutil as _shutil
        final_sdf = output_dir / "result.sdf"
        _shutil.copy2(result.poses_sdf, final_sdf)
        print(f"  ✓ SDF：{final_sdf}")

        split_dir = output_dir / "poses"
        split_poses_to_sdf(result, split_dir)
        pdb_dir = output_dir / "poses_pdb"
        export_poses_pdb(result, pdb_dir)

        # --- Report ---
        if not args.no_report:
            print("▶ 生成 PDF 报告…")
            ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            report_data = ReportData(
                project_name=args.receptor.stem,
                receptor=receptor,
                ligand=ligand,
                pocket=selected,
                result=result,
                user_email="cli@dockmeow.local",
                license_id="CLI-DEV",
                timestamp=ts,
                watermark=False,
            )
            pdf_path = output_dir / "report.pdf"
            generate_pdf_report(report_data, pdf_path, pose_screenshots=[])
            print(f"  ✓ PDF：{pdf_path}")

        print(f"\n{'='*60}")
        print("  对接完成！")
        print(f"  结果目录：{output_dir.resolve()}")
        print(f"{'='*60}\n")

        # Print score table
        print("构象\t结合能(kcal/mol)\tRMSD lb\t\tRMSD ub")
        for i, (s, lb, ub) in enumerate(
            zip(result.scores, result.rmsd_lb, result.rmsd_ub), start=1
        ):
            print(f"{i}\t{s:.2f}\t\t\t{lb:.3f}\t\t{ub:.3f}")
        print()

        return 0

    except DockMeowError as exc:
        print(f"\n错误：{exc.user_message}", file=sys.stderr)
        if exc.suggestion:
            print(f"建议：{exc.suggestion}", file=sys.stderr)
        print(f"\n技术细节（请联系技术支持时附上）：{exc}", file=sys.stderr)
        return 1
    except Exception as exc:
        print(f"\n未知错误：{exc}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())

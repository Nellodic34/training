#!/usr/bin/env python3
"""
Unisce più run del collect_yolo_dataset_node in un unico dataset YOLO.

Uso:
  python3 merge_datasets.py --input ~/dataset_uav_detector --output ~/dataset_merged

Raccoglie tutte le sotto-cartelle (run) dentro --input,
copia immagini e label in un unico dataset con la struttura YOLO standard,
e genera il dataset.yaml per Ultralytics YOLOv8.
"""

import argparse
import os
import shutil
import sys


def find_runs(base_dir: str) -> list[str]:
    """Trova tutte le sotto-cartelle run che contengono images/ e labels/."""
    runs = []
    for entry in sorted(os.listdir(base_dir)):
        run_path = os.path.join(base_dir, entry)
        if os.path.isdir(run_path) and os.path.isdir(os.path.join(run_path, 'images')):
            runs.append(run_path)
    return runs


def merge(input_dir: str, output_dir: str, class_names: list[str], symlink: bool = False) -> None:
    splits = ['train', 'val']
    subdirs = {}
    for split in splits:
        img_dir = os.path.join(output_dir, 'images', split)
        lbl_dir = os.path.join(output_dir, 'labels', split)
        os.makedirs(img_dir, exist_ok=True)
        os.makedirs(lbl_dir, exist_ok=True)
        subdirs[split] = (img_dir, lbl_dir)

    runs = find_runs(input_dir)
    if not runs:
        print(f'Nessun run trovato in {input_dir}')
        sys.exit(1)

    total = 0
    for run in runs:
        run_name = os.path.basename(run)
        for split in splits:
            src_img = os.path.join(run, 'images', split)
            src_lbl = os.path.join(run, 'labels', split)
            if not os.path.isdir(src_img):
                continue

            dst_img, dst_lbl = subdirs[split]

            for fname in os.listdir(src_img):
                # Prefissa il nome del run per evitare collisioni
                dst_name = f'{run_name}_{fname}'
                src_file = os.path.join(src_img, fname)
                dst_file = os.path.join(dst_img, dst_name)

                if symlink:
                    os.symlink(os.path.abspath(src_file), dst_file)
                else:
                    shutil.copy2(src_file, dst_file)

                # Copia la label corrispondente
                label_name = os.path.splitext(fname)[0] + '.txt'
                src_label = os.path.join(src_lbl, label_name)
                dst_label = os.path.join(dst_lbl, f'{run_name}_{label_name}')
                if os.path.isfile(src_label):
                    if symlink:
                        os.symlink(os.path.abspath(src_label), dst_label)
                    else:
                        shutil.copy2(src_label, dst_label)

                total += 1

        print(f'  ✓ {run_name}')

    # Scrivi dataset.yaml
    yaml_path = os.path.join(output_dir, 'dataset.yaml')
    names_str = ', '.join(class_names)
    with open(yaml_path, 'w', encoding='utf-8') as f:
        f.write(f'path: {os.path.abspath(output_dir)}\n')
        f.write('train: images/train\n')
        f.write('val: images/val\n')
        f.write(f'nc: {len(class_names)}\n')
        f.write(f'names: [{names_str}]\n')

    print(f'\nDataset unificato: {output_dir}')
    print(f'Totale immagini: {total}')
    print(f'Run uniti: {len(runs)}')
    print(f'dataset.yaml: {yaml_path}')


def main() -> None:
    parser = argparse.ArgumentParser(description='Unisce più run YOLO in un unico dataset')
    parser.add_argument('--input', '-i', default=os.path.expanduser('~/datasets/uav_detector'),
                        help='Cartella base con le sotto-cartelle dei run')
    parser.add_argument('--output', '-o', default=os.path.expanduser('~/dataset_merged'),
                        help='Cartella di output per il dataset unificato')
    parser.add_argument('--names', '-n', nargs='+', default=['drone'],
                        help='Nomi delle classi (default: drone)')
    parser.add_argument('--symlink', '-s', action='store_true',
                        help='Usa symlink invece di copiare (risparmia spazio disco)')
    args = parser.parse_args()

    merge(args.input, args.output, args.names, args.symlink)


if __name__ == '__main__':
    main()

#!/usr/bin/env python3

import argparse
import csv
import json
import math
import os
import random
from dataclasses import dataclass
from datetime import datetime
from typing import List, Tuple

import numpy as np
from PIL import Image

import torch
import torch.nn as nn
import torch.nn.functional as F
from torch.utils.data import DataLoader, Dataset

try:
    from torchvision import models, transforms
    HAS_TORCHVISION = True
except Exception:
    HAS_TORCHVISION = False


@dataclass
class HeadingSample:
    image_path: str
    sin_yaw: float
    cos_yaw: float


def set_seed(seed: int) -> None:
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    torch.cuda.manual_seed_all(seed)


class HeadingCropDataset(Dataset):
    def __init__(
        self,
        samples: List[HeadingSample],
        image_size: int,
        train: bool,
    ) -> None:
        self.samples = samples
        self.image_size = image_size
        self.train = train

        if HAS_TORCHVISION:
            if train:
                self.transform = transforms.Compose([
                    transforms.Resize((image_size, image_size)),
                    transforms.ColorJitter(brightness=0.25, contrast=0.25, saturation=0.2, hue=0.04),
                    transforms.ToTensor(),
                    transforms.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225]),
                ])
            else:
                self.transform = transforms.Compose([
                    transforms.Resize((image_size, image_size)),
                    transforms.ToTensor(),
                    transforms.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225]),
                ])
        else:
            self.transform = None

    def __len__(self) -> int:
        return len(self.samples)

    def __getitem__(self, idx: int):
        s = self.samples[idx]
        img = Image.open(s.image_path).convert('RGB')

        if self.transform is not None:
            x = self.transform(img)
        else:
            arr = np.array(img.resize((self.image_size, self.image_size)), dtype=np.float32) / 255.0
            arr = np.transpose(arr, (2, 0, 1))
            x = torch.from_numpy(arr)

        y = torch.tensor([s.sin_yaw, s.cos_yaw], dtype=torch.float32)
        y = F.normalize(y, dim=0)
        return x, y


class TinyHeadingCNN(nn.Module):
    def __init__(self) -> None:
        super().__init__()
        self.features = nn.Sequential(
            nn.Conv2d(3, 32, 3, stride=2, padding=1), nn.BatchNorm2d(32), nn.ReLU(inplace=True),
            nn.Conv2d(32, 64, 3, stride=2, padding=1), nn.BatchNorm2d(64), nn.ReLU(inplace=True),
            nn.Conv2d(64, 128, 3, stride=2, padding=1), nn.BatchNorm2d(128), nn.ReLU(inplace=True),
            nn.Conv2d(128, 256, 3, stride=2, padding=1), nn.BatchNorm2d(256), nn.ReLU(inplace=True),
            nn.AdaptiveAvgPool2d((1, 1)),
        )
        self.head = nn.Sequential(
            nn.Flatten(),
            nn.Linear(256, 128),
            nn.ReLU(inplace=True),
            nn.Dropout(0.2),
            nn.Linear(128, 2),
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.head(self.features(x))


def build_model(backbone: str) -> nn.Module:
    if HAS_TORCHVISION and backbone == 'resnet18':
        m = models.resnet18(weights=None)
        m.fc = nn.Linear(m.fc.in_features, 2)
        return m
    return TinyHeadingCNN()


def atan2_deg(sin_vals: torch.Tensor, cos_vals: torch.Tensor) -> torch.Tensor:
    return torch.atan2(sin_vals, cos_vals) * (180.0 / math.pi)


def angular_mae_deg(pred_sc: torch.Tensor, gt_sc: torch.Tensor) -> float:
    pred_sc = F.normalize(pred_sc, dim=1)
    gt_sc = F.normalize(gt_sc, dim=1)

    pred_deg = atan2_deg(pred_sc[:, 0], pred_sc[:, 1])
    gt_deg = atan2_deg(gt_sc[:, 0], gt_sc[:, 1])
    diff = pred_deg - gt_deg
    diff = torch.remainder(diff + 180.0, 360.0) - 180.0
    return float(torch.mean(torch.abs(diff)).item())


def parse_metadata(dataset_root: str, min_bbox_px: float) -> Tuple[List[HeadingSample], List[HeadingSample]]:
    metadata_path = os.path.join(dataset_root, 'metadata.csv')
    if not os.path.exists(metadata_path):
        raise FileNotFoundError(f'metadata.csv not found: {metadata_path}')

    train_samples: List[HeadingSample] = []
    val_samples: List[HeadingSample] = []

    with open(metadata_path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            split = row['split'].strip().lower()
            crop_relpath = row['crop_relpath'].strip()
            bbox_w = float(row['bbox_w'])
            bbox_h = float(row['bbox_h'])
            if min(bbox_w, bbox_h) < min_bbox_px:
                continue

            img_path = os.path.join(dataset_root, crop_relpath)
            if not os.path.exists(img_path):
                continue

            sin_yaw = float(row['sin_yaw_camera'])
            cos_yaw = float(row['cos_yaw_camera'])
            sample = HeadingSample(image_path=img_path, sin_yaw=sin_yaw, cos_yaw=cos_yaw)

            if split == 'train':
                train_samples.append(sample)
            elif split == 'val':
                val_samples.append(sample)

    if not train_samples:
        raise RuntimeError('No valid TRAIN samples found in metadata.csv')
    if not val_samples:
        raise RuntimeError('No valid VAL samples found in metadata.csv')

    return train_samples, val_samples


def run_epoch(model, loader, optimizer, device, train: bool) -> Tuple[float, float]:
    if train:
        model.train()
    else:
        model.eval()

    criterion = nn.MSELoss()
    losses = []
    maes = []

    for x, y in loader:
        x = x.to(device, non_blocking=True)
        y = y.to(device, non_blocking=True)

        with torch.set_grad_enabled(train):
            pred = model(x)
            pred_norm = F.normalize(pred, dim=1)
            loss = criterion(pred_norm, y)

            if train:
                optimizer.zero_grad(set_to_none=True)
                loss.backward()
                optimizer.step()

        losses.append(float(loss.item()))
        maes.append(angular_mae_deg(pred_norm.detach(), y.detach()))

    return float(np.mean(losses)), float(np.mean(maes))


def main() -> None:
    parser = argparse.ArgumentParser(description='Train heading CNN on crop dataset from collect_heading_dataset_node.py')
    parser.add_argument('--dataset_root', type=str, required=True, help='Path to one run folder containing metadata.csv')
    parser.add_argument('--output_dir', type=str, default='~/datasets/uav_heading_models', help='Where to save trained model')
    parser.add_argument('--epochs', type=int, default=30)
    parser.add_argument('--batch_size', type=int, default=64)
    parser.add_argument('--lr', type=float, default=1e-3)
    parser.add_argument('--weight_decay', type=float, default=1e-4)
    parser.add_argument('--image_size', type=int, default=160)
    parser.add_argument('--num_workers', type=int, default=4)
    parser.add_argument('--seed', type=int, default=42)
    parser.add_argument('--min_bbox_px', type=float, default=10.0)
    parser.add_argument('--backbone', type=str, default='resnet18', choices=['resnet18', 'tiny'])
    args = parser.parse_args()

    set_seed(args.seed)

    dataset_root = os.path.abspath(os.path.expanduser(args.dataset_root))
    out_base = os.path.abspath(os.path.expanduser(args.output_dir))
    run_id = datetime.now().strftime('%Y%m%d_%H%M%S')
    out_dir = os.path.join(out_base, f'heading_cnn_{run_id}')
    os.makedirs(out_dir, exist_ok=True)

    train_samples, val_samples = parse_metadata(dataset_root, args.min_bbox_px)

    train_ds = HeadingCropDataset(train_samples, image_size=args.image_size, train=True)
    val_ds = HeadingCropDataset(val_samples, image_size=args.image_size, train=False)

    pin_memory = torch.cuda.is_available()
    train_loader = DataLoader(
        train_ds,
        batch_size=args.batch_size,
        shuffle=True,
        num_workers=args.num_workers,
        pin_memory=pin_memory,
        drop_last=False,
    )
    val_loader = DataLoader(
        val_ds,
        batch_size=args.batch_size,
        shuffle=False,
        num_workers=args.num_workers,
        pin_memory=pin_memory,
        drop_last=False,
    )

    if args.backbone == 'resnet18' and not HAS_TORCHVISION:
        print('[WARN] torchvision not available, falling back to tiny CNN')
        backbone = 'tiny'
    else:
        backbone = args.backbone

    model = build_model(backbone)
    device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
    model.to(device)

    optimizer = torch.optim.AdamW(model.parameters(), lr=args.lr, weight_decay=args.weight_decay)
    scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=max(1, args.epochs))

    best_val_mae = float('inf')
    best_ckpt_path = os.path.join(out_dir, 'best_heading_cnn.pt')

    history = []
    print(f'[INFO] device={device}  backbone={backbone}')
    print(f'[INFO] train_samples={len(train_ds)}  val_samples={len(val_ds)}')

    for epoch in range(1, args.epochs + 1):
        train_loss, train_mae = run_epoch(model, train_loader, optimizer, device, train=True)
        val_loss, val_mae = run_epoch(model, val_loader, optimizer, device, train=False)
        scheduler.step()

        row = {
            'epoch': epoch,
            'train_loss': train_loss,
            'train_mae_deg': train_mae,
            'val_loss': val_loss,
            'val_mae_deg': val_mae,
            'lr': optimizer.param_groups[0]['lr'],
        }
        history.append(row)

        print(
            f"[E{epoch:03d}] "
            f"train_loss={train_loss:.5f} train_mae={train_mae:.2f}deg | "
            f"val_loss={val_loss:.5f} val_mae={val_mae:.2f}deg"
        )

        if val_mae < best_val_mae:
            best_val_mae = val_mae
            torch.save(
                {
                    'model_state_dict': model.state_dict(),
                    'backbone': backbone,
                    'image_size': args.image_size,
                    'best_val_mae_deg': best_val_mae,
                },
                best_ckpt_path,
            )

    with open(os.path.join(out_dir, 'history.json'), 'w', encoding='utf-8') as f:
        json.dump(history, f, indent=2)

    summary = {
        'dataset_root': dataset_root,
        'output_dir': out_dir,
        'model_path': best_ckpt_path,
        'best_val_mae_deg': best_val_mae,
        'epochs': args.epochs,
        'batch_size': args.batch_size,
        'image_size': args.image_size,
        'backbone': backbone,
        'num_train_samples': len(train_ds),
        'num_val_samples': len(val_ds),
    }
    with open(os.path.join(out_dir, 'summary.json'), 'w', encoding='utf-8') as f:
        json.dump(summary, f, indent=2)

    print('\n[DONE] Training finished')
    print(f"[DONE] Best model: {best_ckpt_path}")
    print(f"[DONE] Best val MAE: {best_val_mae:.2f} deg")


if __name__ == '__main__':
    main()

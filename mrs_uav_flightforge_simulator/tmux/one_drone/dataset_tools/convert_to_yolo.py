import os
import pandas as pd
import shutil
import random

# =========================
# CONFIG
# =========================
CSV_PATH = os.path.expanduser("~/universal_datasets/dataset_labels/camp_fall_2.csv")
IMAGES_ROOT = os.path.expanduser("~/universal_datasets/dataset_images")
OUTPUT_ROOT = "real_dataset"

TRAIN_RATIO = 0.95
CLASS_ID = 0

# =========================
# SETUP CARTELLE
# =========================
images_train = os.path.join(OUTPUT_ROOT, "images/train")
images_val = os.path.join(OUTPUT_ROOT, "images/val")
labels_train = os.path.join(OUTPUT_ROOT, "labels/train")
labels_val = os.path.join(OUTPUT_ROOT, "labels/val")

for path in [images_train, images_val, labels_train, labels_val]:
    os.makedirs(path, exist_ok=True)

# =========================
# CARICA CSV
# =========================
df = pd.read_csv(CSV_PATH)

# =========================
# RANDOM SPLIT
# =========================
indices = list(df.index)
random.shuffle(indices)

split_idx = int(len(indices) * TRAIN_RATIO)
train_indices = set(indices[:split_idx])

print(f"Totale immagini: {len(indices)}")
print(f"Train: {len(train_indices)} | Val: {len(indices) - len(train_indices)}")

# =========================
# PROCESSING
# =========================
for idx, row in df.iterrows():
    img_rel_path = row["f"]  # es: camp_fall_2/img_0.jpg
    img_name = os.path.basename(img_rel_path)

    src_img = os.path.join(IMAGES_ROOT, img_rel_path)

    if not os.path.exists(src_img):
        print(f"ERROR: image not found at {src_img}")
        continue

    # bbox (già normalizzate)
    x1 = row["2dx1"]
    y1 = row["2dy1"]
    x2 = row["2dx2"]
    y2 = row["2dy2"]

    # conversione YOLO
    x_center = (x1 + x2) / 2
    y_center = (y1 + y2) / 2
    width = x2 - x1
    height = y2 - y1

    img_base_name = os.path.splitext(img_name)[0]
    
    # scegli train o val
    if idx in train_indices:
        img_dst = os.path.join(images_train, img_name)
        label_dst = os.path.join(labels_train, f"{img_base_name}.txt")
    else:
        img_dst = os.path.join(images_val, img_name)
        label_dst = os.path.join(labels_val, f"{img_base_name}.txt")

    # copia immagine
    shutil.copy2(src_img, img_dst)

    # scrivi label
    with open(label_dst, "w") as f:
        f.write(f"{CLASS_ID} {x_center} {y_center} {width} {height}\n")

# =========================
# CREA dataset.yaml
# =========================
yaml_path = os.path.join(OUTPUT_ROOT, "dataset.yaml")

yaml_content = f"""
path: {os.path.abspath(OUTPUT_ROOT)}

train: images/train
val: images/val

names:
  0: object
"""

with open(yaml_path, "w") as f:
    f.write(yaml_content.strip())

print("\n✅ Dataset YOLO creato in:", OUTPUT_ROOT)
print("📄 dataset.yaml creato!")
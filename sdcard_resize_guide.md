
# SD Card Shrinking & Resizing Guide (DietPi / Raspberry Pi)

This guide explains how to shrink, resize, and expand partitions on a Raspberry Pi SD card.

---

## 1. Check Current Disk Usage
```bash
df -h
```
- Shows current mounted partitions and usage.

```bash
lsblk
```
- Lists block devices and partitions.

---

## 2. Identify Partition Information
```bash
sudo fdisk -l
```
- Find your main root partition (e.g., `/dev/mmcblk0p2`).

---

## 3. Shrinking the Partition (Optional)
> ⚠️ Only needed if you want to make the image smaller for backup/sharing.

1. Unmount the partition:
```bash
sudo umount /dev/mmcblk0p2
```

2. Run `resize2fs` to shrink filesystem before reducing partition size:
```bash
sudo e2fsck -f /dev/mmcblk0p2
sudo resize2fs -M /dev/mmcblk0p2
```

3. Shrink partition using `fdisk`:
```bash
sudo fdisk /dev/mmcblk0
```
- Delete partition **2** (`d` → `2`)
- Recreate partition with smaller size (`n` → `p` → `2`)
- Write changes (`w`)

4. Verify new filesystem size:
```bash
sudo resize2fs /dev/mmcblk0p2
```

---

## 4. Expanding Root Filesystem (After Writing Image to New SD Card)
If you flashed a smaller image and want to use full SD card size:

```bash
sudo fdisk /dev/mmcblk0
```
- Delete partition **2** (`d` → `2`)
- Recreate it using all available space (`n` → `p` → `2` → default start → default end)
- Write changes (`w`)

Then resize filesystem:
```bash
sudo resize2fs /dev/mmcblk0p2
```

---

## 5. Verify Final Size
```bash
df -h
```
- Root (`/`) should now show expanded size.

---

✅ Now your SD card is properly shrunk/expanded depending on your use case.

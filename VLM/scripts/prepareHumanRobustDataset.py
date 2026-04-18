import argparse
import json
import shutil
from pathlib import Path
from typing import Dict, Iterable, List, Tuple


Bbox = Tuple[float, float, float, float]


def ensureDir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def writeYoloLabel(labelPath: Path, imageWidth: int, imageHeight: int, boxes: Iterable[Bbox]) -> None:
    lines: List[str] = []
    for x1, y1, x2, y2 in boxes:
        width = max(1.0, x2 - x1)
        height = max(1.0, y2 - y1)
        centerX = x1 + width / 2.0
        centerY = y1 + height / 2.0

        normalizedCenterX = centerX / imageWidth
        normalizedCenterY = centerY / imageHeight
        normalizedWidth = width / imageWidth
        normalizedHeight = height / imageHeight
        lines.append(
            f'0 {normalizedCenterX:.6f} {normalizedCenterY:.6f} {normalizedWidth:.6f} {normalizedHeight:.6f}'
        )

    labelPath.write_text('\n'.join(lines), encoding='utf-8')


def loadCocoMetadata(annotationPath: Path) -> Dict:
    with open(annotationPath, 'r', encoding='utf-8') as inputFile:
        return json.load(inputFile)


def convertCocoSplit(cocoRoot: Path, splitName: str, outputRoot: Path, useSymlinks: bool) -> int:
    annotationPath = cocoRoot / 'annotations' / f'instances_{splitName}.json'
    imageRoot = cocoRoot / splitName
    if not annotationPath.exists() or not imageRoot.exists():
        return 0

    metadata = loadCocoMetadata(annotationPath)
    personCategoryIds = {item['id'] for item in metadata['categories'] if item['name'] == 'person'}
    imageLookup = {item['id']: item for item in metadata['images']}
    perImageBoxes: Dict[int, List[Bbox]] = {}

    for annotation in metadata['annotations']:
        if annotation.get('category_id') not in personCategoryIds:
            continue
        if annotation.get('iscrowd', 0) != 0:
            continue
        x, y, width, height = annotation['bbox']
        if width < 4 or height < 4:
            continue
        imageId = annotation['image_id']
        perImageBoxes.setdefault(imageId, []).append((x, y, x + width, y + height))

    imageOutRoot = outputRoot / 'images' / ('train' if splitName == 'train2017' else 'val')
    labelOutRoot = outputRoot / 'labels' / ('train' if splitName == 'train2017' else 'val')
    ensureDir(imageOutRoot)
    ensureDir(labelOutRoot)

    convertedCount = 0
    for imageId, boxes in perImageBoxes.items():
        imageInfo = imageLookup.get(imageId)
        if imageInfo is None:
            continue
        sourceImagePath = imageRoot / imageInfo['file_name']
        if not sourceImagePath.exists():
            continue

        destinationStem = f'coco_{sourceImagePath.stem}'
        destinationImagePath = imageOutRoot / f'{destinationStem}{sourceImagePath.suffix.lower()}'
        destinationLabelPath = labelOutRoot / f'{destinationStem}.txt'

        if useSymlinks:
            if not destinationImagePath.exists():
                destinationImagePath.symlink_to(sourceImagePath.resolve())
        else:
            if not destinationImagePath.exists():
                shutil.copy2(sourceImagePath, destinationImagePath)

        writeYoloLabel(destinationLabelPath, int(imageInfo['width']), int(imageInfo['height']), boxes)
        convertedCount += 1

    return convertedCount


def convertCrowdHumanSplit(crowdRoot: Path, splitName: str, outputRoot: Path, useSymlinks: bool) -> int:
    imageRoot = crowdRoot / splitName
    annotationPath = crowdRoot / f'annotation_{splitName}.odgt'
    if not imageRoot.exists() or not annotationPath.exists():
        return 0

    imageOutRoot = outputRoot / 'images' / ('train' if splitName == 'train' else 'val')
    labelOutRoot = outputRoot / 'labels' / ('train' if splitName == 'train' else 'val')
    ensureDir(imageOutRoot)
    ensureDir(labelOutRoot)

    try:
        import cv2
    except Exception as error:
        raise RuntimeError('OpenCV is required to prepare CrowdHuman labels.') from error

    convertedCount = 0
    with open(annotationPath, 'r', encoding='utf-8') as inputFile:
        for line in inputFile:
            row = json.loads(line)
            imageId = row['ID']
            sourceImagePath = imageRoot / f'{imageId}.jpg'
            if not sourceImagePath.exists():
                continue

            image = cv2.imread(str(sourceImagePath))
            if image is None:
                continue
            imageHeight, imageWidth = image.shape[:2]

            boxes: List[Bbox] = []
            for gtBox in row.get('gtboxes', []):
                if gtBox.get('tag') != 'person':
                    continue
                extra = gtBox.get('extra', {})
                if int(extra.get('ignore', 0)) != 0:
                    continue
                fullBox = gtBox.get('fbox')
                if not fullBox or len(fullBox) != 4:
                    continue
                x, y, width, height = fullBox
                if width < 4 or height < 4:
                    continue
                boxes.append((x, y, x + width, y + height))

            if not boxes:
                continue

            destinationStem = f'crowdhuman_{imageId}'
            destinationImagePath = imageOutRoot / f'{destinationStem}.jpg'
            destinationLabelPath = labelOutRoot / f'{destinationStem}.txt'

            if useSymlinks:
                if not destinationImagePath.exists():
                    destinationImagePath.symlink_to(sourceImagePath.resolve())
            else:
                if not destinationImagePath.exists():
                    shutil.copy2(sourceImagePath, destinationImagePath)

            writeYoloLabel(destinationLabelPath, imageWidth, imageHeight, boxes)
            convertedCount += 1

    return convertedCount


def convertWiderPersonSplit(widerRoot: Path, outputRoot: Path, useSymlinks: bool) -> int:
    imageRoot = widerRoot / 'Images'
    annotationRoot = widerRoot / 'Annotations'
    trainList = widerRoot / 'train.txt'
    valList = widerRoot / 'val.txt'
    if not imageRoot.exists() or not annotationRoot.exists() or not trainList.exists() or not valList.exists():
        return 0

    try:
        import cv2
    except Exception as error:
        raise RuntimeError('OpenCV is required to prepare WiderPerson labels.') from error

    convertedCount = 0
    for listPath, subsetName in [(trainList, 'train'), (valList, 'val')]:
        imageOutRoot = outputRoot / 'images' / subsetName
        labelOutRoot = outputRoot / 'labels' / subsetName
        ensureDir(imageOutRoot)
        ensureDir(labelOutRoot)

        with open(listPath, 'r', encoding='utf-8') as inputFile:
            for line in inputFile:
                imageId = line.strip()
                if not imageId:
                    continue
                sourceImagePath = imageRoot / f'{imageId}.jpg'
                sourceLabelPath = annotationRoot / f'{imageId}.jpg.txt'
                if not sourceImagePath.exists() or not sourceLabelPath.exists():
                    continue

                image = cv2.imread(str(sourceImagePath))
                if image is None:
                    continue
                imageHeight, imageWidth = image.shape[:2]

                boxes: List[Bbox] = []
                with open(sourceLabelPath, 'r', encoding='utf-8') as labelFile:
                    rows = [row.strip() for row in labelFile.readlines() if row.strip()]
                for row in rows[1:]:
                    values = row.split()
                    if len(values) != 5:
                        continue
                    classLabel, x1, y1, x2, y2 = values
                    if int(classLabel) not in (1, 2, 3):
                        continue
                    boxes.append((float(x1), float(y1), float(x2), float(y2)))

                if not boxes:
                    continue

                destinationStem = f'widerperson_{imageId}'
                destinationImagePath = imageOutRoot / f'{destinationStem}.jpg'
                destinationLabelPath = labelOutRoot / f'{destinationStem}.txt'

                if useSymlinks:
                    if not destinationImagePath.exists():
                        destinationImagePath.symlink_to(sourceImagePath.resolve())
                else:
                    if not destinationImagePath.exists():
                        shutil.copy2(sourceImagePath, destinationImagePath)

                writeYoloLabel(destinationLabelPath, imageWidth, imageHeight, boxes)
                convertedCount += 1

    return convertedCount


def writeDatasetYaml(outputRoot: Path) -> None:
    yamlPath = outputRoot / 'humanRobustMerged.yaml'
    yamlText = '\n'.join([
        f'path: {outputRoot.as_posix()}',
        'autodownload: false',
        'train: images/train',
        'val: images/val',
        'test:',
        'nc: 1',
        'names:',
        '  0: person',
    ])
    yamlPath.write_text(yamlText + '\n', encoding='utf-8')


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--outdir', default='datasets/humanRobust')
    parser.add_argument('--cocoRoot', default=None)
    parser.add_argument('--crowdHumanRoot', default=None)
    parser.add_argument('--widerPersonRoot', default=None)
    parser.add_argument('--copyImages', action='store_true')
    args = parser.parse_args()

    outputRoot = Path(args.outdir)
    ensureDir(outputRoot / 'images' / 'train')
    ensureDir(outputRoot / 'images' / 'val')
    ensureDir(outputRoot / 'labels' / 'train')
    ensureDir(outputRoot / 'labels' / 'val')

    useSymlinks = not args.copyImages

    totalConverted = 0
    if args.cocoRoot:
        cocoRoot = Path(args.cocoRoot)
        totalConverted += convertCocoSplit(cocoRoot, 'train2017', outputRoot, useSymlinks)
        totalConverted += convertCocoSplit(cocoRoot, 'val2017', outputRoot, useSymlinks)

    if args.crowdHumanRoot:
        crowdRoot = Path(args.crowdHumanRoot)
        totalConverted += convertCrowdHumanSplit(crowdRoot, 'train', outputRoot, useSymlinks)
        totalConverted += convertCrowdHumanSplit(crowdRoot, 'val', outputRoot, useSymlinks)

    if args.widerPersonRoot:
        widerRoot = Path(args.widerPersonRoot)
        totalConverted += convertWiderPersonSplit(widerRoot, outputRoot, useSymlinks)

    writeDatasetYaml(outputRoot)
    print(f'Prepared {totalConverted} labeled images into {outputRoot}')
    print(f'Use dataset config: {outputRoot / "humanRobustMerged.yaml"}')


if __name__ == '__main__':
    main()

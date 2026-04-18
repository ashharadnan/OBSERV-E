import argparse
from pathlib import Path
import zipfile
import requests


cocoFiles = {
    'train2017.zip': 'http://images.cocodataset.org/zips/train2017.zip',
    'val2017.zip': 'http://images.cocodataset.org/zips/val2017.zip',
    'annotations_trainval2017.zip': 'http://images.cocodataset.org/annotations/annotations_trainval2017.zip',
}

motFiles = {
    'MOT17.zip': 'https://motchallenge.net/data/MOT17.zip',
}


def downloadFile(url: str, destinationPath: Path) -> None:
    destinationPath.parent.mkdir(parents=True, exist_ok=True)
    with requests.get(url, stream=True, timeout=120) as response:
        response.raise_for_status()
        with open(destinationPath, 'wb') as outputFile:
            for chunk in response.iter_content(chunk_size=1024 * 1024):
                if chunk:
                    outputFile.write(chunk)


def maybeExtract(zipPath: Path) -> None:
    with zipfile.ZipFile(zipPath, 'r') as archive:
        archive.extractall(zipPath.parent)


def printCrowdHumanInstructions(root: Path) -> None:
    crowdRoot = root / 'crowdHuman'
    crowdRoot.mkdir(parents=True, exist_ok=True)
    print('CrowdHuman uses Google Drive / Baidu links from the official site.')
    print('Download these into datasets/crowdHuman/ and extract them there:')
    print('  - CrowdHuman_train01.zip')
    print('  - CrowdHuman_train02.zip')
    print('  - CrowdHuman_train03.zip')
    print('  - CrowdHuman_val.zip')
    print('  - annotation_train.odgt')
    print('  - annotation_val.odgt')
    print(f'Expected destination: {crowdRoot.resolve()}')


def printWiderPersonInstructions(root: Path) -> None:
    widerRoot = root / 'widerPerson'
    widerRoot.mkdir(parents=True, exist_ok=True)
    print('WiderPerson also uses official Google Drive / Baidu links.')
    print('Download and extract the dataset into datasets/widerPerson/.')
    print('Expected files include Images/, Annotations/, train.txt, and val.txt.')
    print(f'Expected destination: {widerRoot.resolve()}')


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', default='datasets')
    parser.add_argument('--coco', action='store_true')
    parser.add_argument('--mot17', action='store_true')
    parser.add_argument('--crowdHuman', action='store_true')
    parser.add_argument('--widerPerson', action='store_true')
    parser.add_argument('--extract', action='store_true')
    args = parser.parse_args()

    root = Path(args.root)
    didSomething = False

    if args.coco:
        didSomething = True
        cocoRoot = root / 'coco'
        for fileName, url in cocoFiles.items():
            destinationPath = cocoRoot / fileName
            downloadFile(url, destinationPath)
            if args.extract:
                maybeExtract(destinationPath)
            print(f'Downloaded {destinationPath}')

    if args.mot17:
        didSomething = True
        motRoot = root / 'mot17'
        for fileName, url in motFiles.items():
            destinationPath = motRoot / fileName
            downloadFile(url, destinationPath)
            if args.extract:
                maybeExtract(destinationPath)
            print(f'Downloaded {destinationPath}')

    if args.crowdHuman:
        didSomething = True
        printCrowdHumanInstructions(root)

    if args.widerPerson:
        didSomething = True
        printWiderPersonInstructions(root)

    if not didSomething:
        raise SystemExit('Pass one or more of: --coco --mot17 --crowdHuman --widerPerson')


if __name__ == '__main__':
    main()

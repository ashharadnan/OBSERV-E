import argparse
from pathlib import Path
import sys
import cv2
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from humanFollower.pipeline import HumanFollowerPipeline


def applyOverrides(configPath: Path, args) -> Path:
    with open(configPath, 'r', encoding='utf-8') as inputFile:
        config = yaml.safe_load(inputFile)

    config['tracking']['detectEvery'] = args.detectEvery
    config['tracking']['selectionMode'] = args.selectionMode
    config['output']['outputMode'] = args.outputMode
    config['output']['udpHost'] = args.udpHost
    config['output']['udpPort'] = args.udpPort
    if args.jsonlPath is not None:
        config['output']['jsonlPath'] = args.jsonlPath

    temporaryPath = configPath.parent / '_runtime_video_config.yaml'
    with open(temporaryPath, 'w', encoding='utf-8') as outputFile:
        yaml.safe_dump(config, outputFile, sort_keys=False)
    return temporaryPath


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--model', required=True)
    parser.add_argument('--video', required=True)
    parser.add_argument('--save', default='outputs/annotatedVideo.mp4')
    parser.add_argument('--config', default='configs/default.yaml')
    parser.add_argument('--detectEvery', type=int, default=2)
    parser.add_argument('--selectionMode', choices=['closestToCenter', 'highestConfidence', 'largest'], default='closestToCenter')
    parser.add_argument('--outputMode', choices=['stdout', 'udp', 'jsonl', 'stdoutMatrix', 'udpMatrix'], default='jsonl')
    parser.add_argument('--udpHost', default='127.0.0.1')
    parser.add_argument('--udpPort', type=int, default=5005)
    parser.add_argument('--jsonlPath', default='outputs/gimbalStates.jsonl')
    args = parser.parse_args()

    configPath = applyOverrides(Path(args.config), args)
    pipeline = HumanFollowerPipeline(modelPath=args.model, configPath=str(configPath))
    capture = cv2.VideoCapture(args.video)

    if not capture.isOpened():
        raise RuntimeError(f'Unable to open video {args.video}')

    outputPath = Path(args.save)
    outputPath.parent.mkdir(parents=True, exist_ok=True)

    frameWidth = int(capture.get(cv2.CAP_PROP_FRAME_WIDTH))
    frameHeight = int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT))
    fps = capture.get(cv2.CAP_PROP_FPS)
    if fps <= 0:
        fps = 30.0

    writer = cv2.VideoWriter(
        str(outputPath),
        cv2.VideoWriter_fourcc(*'mp4v'),
        fps,
        (frameWidth, frameHeight),
    )

    try:
        while True:
            ok, frame = capture.read()
            if not ok:
                break
            result = pipeline.processFrame(frame, publishState=True, drawUi=True)
            writer.write(result['frame'])
    finally:
        writer.release()
        capture.release()
        pipeline.close()
        cv2.destroyAllWindows()


if __name__ == '__main__':
    main()

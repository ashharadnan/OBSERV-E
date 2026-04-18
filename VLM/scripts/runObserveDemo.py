import argparse
from pathlib import Path
import os
import sys
import cv2
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from humanFollower.pipeline import HumanFollowerPipeline
from humanFollower.observEPipeline import ObservePipeline


def applyOverrides(configPath: Path, args) -> Path:
    with open(configPath, 'r', encoding='utf-8') as inputFile:
        config = yaml.safe_load(inputFile)

    config['tracking']['detectEvery'] = args.detectEvery
    config['tracking']['selectionMode'] = args.selectionMode
    config['tracking']['commandLookaheadSec'] = args.predictionLeadMs / 1000.0
    config['output']['outputMode'] = 'jsonl' if args.jsonlPath else 'stdout'
    if args.jsonlPath:
        config['output']['jsonlPath'] = args.jsonlPath
    config['observe']['userName'] = args.userName
    config['observe']['locationLabel'] = args.locationLabel

    if 'vlm' not in config:
        config['vlm'] = {}
    if args.enableVlm:
        config['vlm']['enabled'] = True
    if args.groqModel:
        config['vlm']['model'] = args.groqModel
    if args.groqApiKeyEnv:
        config['vlm']['apiKeyEnv'] = args.groqApiKeyEnv
    if args.groqApiKey:
        config['vlm']['apiKey'] = args.groqApiKey

    temporaryPath = configPath.parent / '_runtime_observe_config.yaml'
    with open(temporaryPath, 'w', encoding='utf-8') as outputFile:
        yaml.safe_dump(config, outputFile, sort_keys=False)
    return temporaryPath


def stackFrames(frameA, frameB):
    if frameA.shape[0] != frameB.shape[0]:
        height = min(frameA.shape[0], frameB.shape[0])
        widthA = int(frameA.shape[1] * (height / frameA.shape[0]))
        widthB = int(frameB.shape[1] * (height / frameB.shape[0]))
        frameA = cv2.resize(frameA, (widthA, height))
        frameB = cv2.resize(frameB, (widthB, height))
    return cv2.hconcat([frameA, frameB])


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--trackModel', required=True)
    parser.add_argument('--hazardModel', default=None)
    parser.add_argument('--trackingCamera', type=int, default=0)
    parser.add_argument('--hazardCamera', type=int, default=-1)
    parser.add_argument('--video', default=None)
    parser.add_argument('--hazardVideo', default=None)
    parser.add_argument('--config', default='configs/observeMvp.yaml')
    parser.add_argument('--detectEvery', type=int, default=2)
    parser.add_argument('--selectionMode', choices=['closestToCenter', 'highestConfidence', 'largest'], default='closestToCenter')
    parser.add_argument('--predictionLeadMs', type=float, default=8.0)
    parser.add_argument('--jsonlPath', default='outputs/observeTrackingStates.jsonl')
    parser.add_argument('--save', default='outputs/observeDemo.mp4')
    parser.add_argument('--headless', action='store_true')
    parser.add_argument('--userName', default='User')
    parser.add_argument('--locationLabel', default='demo area')
    parser.add_argument('--voiceText', default='')
    parser.add_argument('--enableVlm', action='store_true')
    parser.add_argument('--groqModel', default=None)
    parser.add_argument('--groqApiKeyEnv', default='GROQ_API_KEY')
    parser.add_argument('--groqApiKey', default='')
    args = parser.parse_args()

    if args.groqApiKey and args.groqApiKeyEnv and args.groqApiKeyEnv != 'GROQ_API_KEY':
        os.environ[args.groqApiKeyEnv] = args.groqApiKey

    configPath = applyOverrides(Path(args.config), args)
    trackingPipeline = HumanFollowerPipeline(modelPath=args.trackModel, configPath=str(configPath))
    observePipeline = ObservePipeline(
        trackingPipeline=trackingPipeline,
        configPath=str(configPath),
        hazardModelPath=args.hazardModel or args.trackModel,
    )

    if args.video:
        trackCapture = cv2.VideoCapture(args.video)
        hazardCapture = cv2.VideoCapture(args.hazardVideo) if args.hazardVideo else None
    else:
        trackCapture = cv2.VideoCapture(args.trackingCamera)
        hazardCapture = cv2.VideoCapture(args.hazardCamera) if args.hazardCamera >= 0 else None

    if not trackCapture.isOpened():
        raise RuntimeError('Unable to open tracking source')
    if hazardCapture is not None and not hazardCapture.isOpened():
        raise RuntimeError('Unable to open hazard source')

    writer = None
    outputPath = Path(args.save)
    outputPath.parent.mkdir(parents=True, exist_ok=True)

    try:
        while True:
            okTrack, trackingFrame = trackCapture.read()
            if not okTrack:
                break

            hazardFrame = None
            if hazardCapture is not None:
                okHazard, hazardFrame = hazardCapture.read()
                if not okHazard:
                    break

            result = observePipeline.process(trackingFrame, hazardFrame=hazardFrame, voiceText=args.voiceText)
            combinedFrame = stackFrames(result['trackingFrame'], result['hazardFrame'])

            if writer is None:
                fps = trackCapture.get(cv2.CAP_PROP_FPS)
                if fps <= 0:
                    fps = 20.0
                writer = cv2.VideoWriter(
                    str(outputPath),
                    cv2.VideoWriter_fourcc(*'mp4v'),
                    fps,
                    (combinedFrame.shape[1], combinedFrame.shape[0]),
                )

            writer.write(combinedFrame)
            state = result['state']
            trackingPayload = result['trackingPayload']
            frameSummary = {
                'frameIndex': state['frameIndex'],
                'riskScore': round(state['riskScore'], 3),
                'eventLevel': state['eventLevel'],
                'immediateAlert': state['immediateAlert'],
                'summary': state['summary'],
                'vlmSummary': state.get('vlmSummary'),
                'reasons': state['reasons'],
                'ttsText': state.get('ttsText'),
                'kalmanState': trackingPayload.get('kalmanState'),
                'predictedKalmanState': trackingPayload.get('predictedKalmanState'),
                'actualBoxState': trackingPayload.get('actualBoxState'),
            }
            print(frameSummary, flush=True)
            for speechEvent in state.get('speechEvents', []):
                print(
                    f"[tts][frame {state['frameIndex']}] {speechEvent['eventType']}: {speechEvent['text']}",
                    flush=True,
                )

            if not args.headless:
                cv2.imshow('OBSERV-E demo', combinedFrame)
                pressed = cv2.waitKey(1) & 0xFF
                if pressed in (27, ord('q')):
                    break
    finally:
        if writer is not None:
            writer.release()
        trackCapture.release()
        if hazardCapture is not None:
            hazardCapture.release()
        observePipeline.close()
        trackingPipeline.close()
        cv2.destroyAllWindows()


if __name__ == '__main__':
    main()

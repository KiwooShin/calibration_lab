import argparse,json
from pathlib import Path
from .dataset import simulate
from .solver import calibrate


def main():
    parser=argparse.ArgumentParser(description='Calibrate two arm chains from head-camera 3D landmarks')
    parser.add_argument('--input',type=Path,help='Perception dataset JSON; omit for synthetic demo')
    parser.add_argument('--output',type=Path,default=Path('artifacts/calibration.json'))
    parser.add_argument('--example',type=Path,help='Write a synthetic input dataset and exit')
    args=parser.parse_args()
    if args.example:
        data,_=simulate();args.example.parent.mkdir(parents=True,exist_ok=True)
        args.example.write_text(json.dumps(data,indent=2));print(args.example);return
    if args.input:
        data=json.loads(args.input.read_text());result=calibrate(data)
    else:
        data,truth=simulate();result=calibrate(data,'synthetic',truth)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(result,allow_nan=False));print(args.output)
    print(f'Validation observation RMS: {result["initial"]["validation_rms_mm"]:.3f} → {result["final"]["validation_rms_mm"]:.3f} mm')
    print(f'Local identifiability: {result["rank"]}/18')


if __name__=='__main__':main()

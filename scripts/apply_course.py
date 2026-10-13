"""Import a local, git-ignored owner configuration into the chosen Compose project."""
import argparse
from pathlib import Path
from compose_tools import Compose


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('config')
    parser.add_argument('--project')
    args=parser.parse_args()
    Compose(args.project).run('exec','-T','web','python','-m','app.setup_course',input=Path(args.config).read_bytes())

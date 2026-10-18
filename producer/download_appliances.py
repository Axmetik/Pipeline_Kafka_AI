"""Download the original UCI CSV without overwriting an existing dataset."""
import argparse
from io import BytesIO
from pathlib import Path
from zipfile import ZipFile
import requests
from producer.appliances_dataset import DATASET_URL, dataset_sha256


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", default="data/energy/raw/energydata_complete.csv")
    args = parser.parse_args()
    path = Path(args.output)
    if path.exists():
        raise FileExistsError(f"Dataset already exists: {path}")
    response = requests.get(DATASET_URL, timeout=60)
    response.raise_for_status()
    with ZipFile(BytesIO(response.content)) as archive:
        content = archive.read("energydata_complete.csv")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as file:
        file.write(content)
    print(f"Downloaded {path}; sha256={dataset_sha256(path)}")


if __name__ == "__main__":
    main()

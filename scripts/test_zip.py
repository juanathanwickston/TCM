import zipfile
from pathlib import Path

zip_path = Path(r'Payroc Training Catalogue/POS/onePOS/01_Onboarding/02_Instructor Led - Virtual/onePOS Support Training.zip')

if zip_path.exists():
    print(f"ZIP exists: {zip_path}")
    print(f"Size: {zip_path.stat().st_size} bytes")
    
    try:
        with zipfile.ZipFile(zip_path, 'r') as zf:
            files = [i for i in zf.infolist() if not i.is_dir()]
            print(f"File count inside ZIP: {len(files)}")
            for f in files[:10]:
                print(f"  - {f.filename}")
    except Exception as e:
        print(f"Error reading ZIP: {e}")
else:
    print(f"ZIP not found: {zip_path}")

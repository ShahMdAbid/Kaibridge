import sys

site_dir = r"C:\Users\HP\OneDrive\Documents\KiCad\10.0\3rdparty\Python311\site-packages"
if site_dir not in sys.path:
    sys.path.insert(0, site_dir)

import easyeda2kicad.easyeda.easyeda_api as ea
ea.API_ENDPOINT = "https://lceda.cn/api/products/{lcsc_id}/components"
ea.ENDPOINT_3D_MODEL = "https://modules.easyeda.com/3dmodel/{uuid}"
ea.ENDPOINT_3D_MODEL_STEP = "https://modules.easyeda.com/qAxj6KHrDKw4blvCG8QJPs7Y/{uuid}"

from easyeda2kicad.__main__ import main

if __name__ == "__main__":
    main()

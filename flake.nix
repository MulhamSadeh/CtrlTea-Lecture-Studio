{
  description = "Ctrl+Tea local Arabic lecture studio";
  inputs.nixpkgs.url = "github:NixOS/nixpkgs/26f4107e47e3ad0ffd0db220469ba83b6f6d96e8";
  outputs = { self, nixpkgs }:
    let
      systems = [ "x86_64-linux" "aarch64-linux" ];
      eachSystem = nixpkgs.lib.genAttrs systems;
    in {
      devShells = eachSystem (system:
        let
          pkgs = import nixpkgs { inherit system; };
          python = pkgs.python313.withPackages (ps: with ps; [
            fastapi uvicorn pydantic python-multipart pymupdf python-docx lxml
            matplotlib numpy cairosvg jsonschema pytest httpx playwright
            # Required by Task04 account modules even when AUTH_MODE=local.
            psycopg argon2-cffi email-validator pillow
            # Required for optional DB migration and account validation tools.
            sqlalchemy alembic
          ]);
          ocr = pkgs.tesseract.override { enableLanguages = [ "ara" "eng" ]; };
          fonts = pkgs.makeFontsConf { fontDirectories = [ ./frontend/public/fonts ./assets/fonts pkgs.lmodern ]; };
        in { default = pkgs.mkShell {
          packages = [ python pkgs.nodejs_22 pkgs.pandoc pkgs.libreoffice ocr pkgs.fontconfig pkgs.chromium ];
          FONTCONFIG_FILE = fonts;
          CHROMIUM_EXECUTABLE_PATH = "${pkgs.chromium}/bin/chromium";
          shellHook = ''
            export PYTHONPATH="$PWD/backend''${PYTHONPATH:+:$PYTHONPATH}"
            echo "Ctrl+Tea: python scripts/start.py"
          '';
        }; });
    };
}

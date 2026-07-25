; Instalador de "Línea de Costa" (Guardamar del Segura) para Windows.
;
; Antes de compilar este script hay que generar los ejecutables que empaqueta:
;   cd frontend && npm run build && cd ..
;   cd backend
;   pyinstaller desktop_launcher.spec
;   pyinstaller download_sam.spec
;   cd ..
; Esto deja backend\dist\LineaDeCosta\ (la app) y backend\dist\download_sam.exe
; (el descargador del modelo SAM, ver download_sam.py) — las rutas [Files] de
; abajo asumen esa estructura por defecto de PyInstaller (sin --distpath).
;
; Compilar con Inno Setup (https://jrsoftware.org/isinfo.php):
;   ISCC.exe cv-lit.iss
; El instalador resultante queda en installer\output\LineaDeCosta-Setup.exe.
;
; El checkpoint del modelo SAM (~2.4 GB) NO se empaqueta aquí — la app
; funciona sin él (segmentación por color/Otsu, ver get_segmenter() en
; backend/main.py) y se descarga aparte, opcionalmente, con download_sam.exe.
; Así el instalador se queda en ~1-1.5 GB en vez de arrastrar ese archivo.

#define MyAppName "Linea de Costa"
#define MyAppVersion "0.1.0"
#define MyAppPublisher "Universidad de Alicante"
#define MyAppExeName "LineaDeCosta.exe"

[Setup]
AppId={{1094E9EB-DEC0-441E-B9D8-2DC29FB27E4E}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
OutputDir=output
OutputBaseFilename=LineaDeCosta-Setup
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
ArchitecturesInstallIn64BitMode=x64compatible
; Los datos del usuario (calibración, imágenes, logs) van a %LOCALAPPDATA%
; (ver backend/config.py), NO a la carpeta de instalación — así no hace
; falta privilegios de administrador para usar la app día a día, aunque se
; instale en Program Files.
PrivilegesRequired=lowest

[Languages]
Name: "spanish"; MessagesFile: "compiler:Languages\Spanish.isl"

[Tasks]
Name: "desktopicon"; Description: "Crear un acceso directo en el escritorio"; GroupDescription: "Accesos directos:"
Name: "descargar_sam"; Description: "Descargar el modelo de segmentación con IA (SAM, ~2.4 GB adicionales). Se puede omitir ahora y descargar más tarde desde el menú inicio."; GroupDescription: "Segmentación con IA (opcional):"; Flags: unchecked

[Files]
Source: "..\backend\dist\LineaDeCosta\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "..\backend\dist\download_sam.exe"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\Descargar modelo de IA (SAM)"; Filename: "{app}\download_sam.exe"
Name: "{group}\Desinstalar {#MyAppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
; Se ejecuta automáticamente tras la instalación SOLO si se marcó la tarea de
; arriba — con ventana propia (download_sam.py tiene su propia consola con
; progreso), bloqueando el asistente hasta terminar para no dejarlo huérfano.
Filename: "{app}\download_sam.exe"; StatusMsg: "Descargando el modelo de segmentación con IA (SAM)…"; Tasks: descargar_sam; Flags: waituntilterminated
; Casilla estándar de "abrir la app" en la página final del asistente.
Filename: "{app}\{#MyAppExeName}"; Description: "Abrir {#MyAppName}"; Flags: nowait postinstall skipifsilent

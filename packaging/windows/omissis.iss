; Installer di Omissis per Windows (Inno Setup 6). Lo compila build_windows.py, che passa versione, cartelle e icona:
;   ISCC /DVersione=0.1.0 /DSorgente=<cartella preparata> /DUscita=<cartella di uscita> /DIcona=<file .ico> omissis.iss
;
; Si installa per il solo utente, senza diritti di amministratore, in %LOCALAPPDATA%\Programs\Omissis.
; I dati dell'utente (archivio dei valori, impostazioni, liste, modello scaricato) stanno in %LOCALAPPDATA%\Omissis
; e l'installer non li tocca: un aggiornamento riscrive solo la cartella del programma.

#ifndef Versione
  #define Versione "0.0.0"
#endif
#ifndef Sorgente
  #define Sorgente "..\..\build\windows\Omissis"
#endif
#ifndef Uscita
  #define Uscita "..\..\dist"
#endif
#ifndef Icona
  #define Icona "..\..\build\windows\Omissis\omissis.ico"
#endif
#define Avvio "{app}\python\Omissis.exe"

[Setup]
AppId={{6F0B6E0C-3B0B-4E57-9C55-0D1E5A7C2F41}
AppName=Omissis
AppVersion={#Versione}
AppVerName=Omissis {#Versione}
AppPublisher=Francesco Gruner
AppPublisherURL=https://omissis.eu
AppSupportURL=https://omissis.eu
AppUpdatesURL=https://github.com/francescogruner/omissis/releases
VersionInfoVersion={#Versione}
DefaultDirName={localappdata}\Programs\Omissis
DisableProgramGroupPage=yes
DisableDirPage=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0.17763
OutputDir={#Uscita}
OutputBaseFilename=Omissis-{#Versione}-setup
SetupIconFile={#Icona}
UninstallDisplayIcon={app}\omissis.ico
UninstallDisplayName=Omissis
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
CloseApplications=no
UsePreviousTasks=yes

[Languages]
Name: "it"; MessagesFile: "compiler:Languages\Italian.isl"
Name: "en"; MessagesFile: "compiler:Default.isl"

[CustomMessages]
it.AllAccesso=Avvia Omissis all'accesso a Windows
en.AllAccesso=Start Omissis when I sign in to Windows
it.SulDesktop=Crea un'icona sul desktop
en.SulDesktop=Create a desktop icon
it.AvviaOra=Avvia Omissis
en.AvviaOra=Start Omissis
it.TogliDati=Eliminare anche i dati di Omissis su questo PC?%n%nSono l'archivio dei valori sostituiti, le impostazioni, le liste personali, il modello scaricato e il certificato del proxy (che viene tolto anche da Windows).%n%nSenza l'archivio i segnaposto nei documenti e nelle conversazioni già anonimizzati non si potranno più riportare ai valori veri.
en.TogliDati=Also delete the Omissis data on this PC?%n%nThat is the vault of replaced values, the settings, your personal lists, the downloaded model and the proxy certificate (which is also removed from Windows).%n%nWithout the vault, placeholders in documents and conversations you already anonymised can no longer be turned back into the real values.

[Tasks]
Name: "avvio"; Description: "{cm:AllAccesso}"
Name: "desktop"; Description: "{cm:SulDesktop}"; Flags: unchecked

[InstallDelete]
; la versione precedente va tolta per intero: file rimasti di librerie vecchie accanto a quelle nuove fanno danni
Type: filesandordirs; Name: "{app}\python"
Type: filesandordirs; Name: "{app}\app"
Type: filesandordirs; Name: "{app}\model"

[Files]
Source: "{#Sorgente}\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs ignoreversion

[Icons]
Name: "{autoprograms}\Omissis"; Filename: "{#Avvio}"; Parameters: """{app}\app\panel.py"""; WorkingDir: "{app}\app"; IconFilename: "{app}\omissis.ico"
Name: "{autodesktop}\Omissis"; Filename: "{#Avvio}"; Parameters: """{app}\app\panel.py"""; WorkingDir: "{app}\app"; IconFilename: "{app}\omissis.ico"; Tasks: desktop

[Registry]
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; ValueName: "Omissis"; ValueData: """{app}\python\Omissis.exe"" ""{app}\app\panel.py"" --no-browser"; Flags: uninsdeletevalue; Tasks: avvio

[Run]
Filename: "{#Avvio}"; Parameters: """{app}\app\panel.py"""; WorkingDir: "{app}\app"; Description: "{cm:AvviaOra}"; Flags: nowait postinstall skipifsilent
; aggiornamento lanciato dal programma stesso (/RIAVVIA=1): alla fine lo si riapre, senza aprire il browser
Filename: "{#Avvio}"; Parameters: """{app}\app\panel.py"" --no-browser"; WorkingDir: "{app}\app"; Flags: nowait; Check: DaRiavviare

[UninstallDelete]
; i file che Python scrive accanto al codice
Type: filesandordirs; Name: "{app}\python"
Type: filesandordirs; Name: "{app}\app"
Type: filesandordirs; Name: "{app}\model"

[Code]
function DaRiavviare: Boolean;
begin
  Result := ExpandConstant('{param:RIAVVIA|0}') = '1';
end;

{ Chiude le copie di Omissis in esecuzione DA QUESTA cartella (pannello, motore, proxy): i loro file stanno per essere
  sostituiti. Altre copie, per esempio quella di chi sviluppa lanciata dai sorgenti, non vengono toccate. }
procedure ChiudiOmissis;
var
  Esito: Integer;
  Cartella: String;
begin
  Cartella := ExpandConstant('{app}');
  StringChangeEx(Cartella, '''', '''''', True);
  Exec('powershell.exe',
       '-NoProfile -NonInteractive -WindowStyle Hidden -Command "Get-Process | Where-Object { $_.Path -like ''' + Cartella + '\*'' } | Stop-Process -Force; Start-Sleep -Milliseconds 800"',
       '', SW_HIDE, ewWaitUntilTerminated, Esito);
end;

function PrepareToInstall(var NeedsRestart: Boolean): String;
begin
  ChiudiOmissis;
  Result := '';
end;

function InitializeUninstall: Boolean;
begin
  ChiudiOmissis;
  Result := True;
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  Esito: Integer;
begin
  if (CurUninstallStep = usPostUninstall) and (not UninstallSilent) then
    if MsgBox(CustomMessage('TogliDati'), mbConfirmation, MB_YESNO or MB_DEFBUTTON2) = IDYES then
    begin
      Exec('certutil.exe', '-user -delstore Root mitmproxy', '', SW_HIDE, ewWaitUntilTerminated, Esito);
      DelTree(ExpandConstant('{localappdata}\Omissis'), True, True, True);
    end;
end;

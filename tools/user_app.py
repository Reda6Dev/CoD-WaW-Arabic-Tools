# -*- coding: utf-8 -*-
"""End-user installer (console, English prompts because the Windows console cannot show Arabic).
Used by تركيب_للاعبين_بايثون.bat (needs Python) or as the single WaW_Arabic.exe built by بناء_ملف_exe.bat.
It finds the game folder by itself, or opens a 'Browse' window, or accepts a folder dragged onto it."""
import sys, os, subprocess
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.argv = [sys.argv[0], 'user'] + sys.argv[1:]       # cod4.py looks at argv[2:] for options
import cod4
cod4.LANG = 'en'

def is_game(p): return bool(p) and os.path.isdir(os.path.join(p, 'zone', 'english')) and os.path.isdir(os.path.join(p, 'main'))

def find_games(extra_roots=None):
    """Looks for a folder containing zone/english in the usual places (all drives, Steam libraries, registry)."""
    roots = list(extra_roots or [])
    if os.name == 'nt':
        for d in 'CDEFGHIJKLMNOPQRSTUVWXYZ':
            if not os.path.exists(d + ':\\'): continue
            for sub in ('', 'Games', 'Program Files (x86)', 'Program Files', 'Steam\\steamapps\\common', 'SteamLibrary\\steamapps\\common',
                        'Program Files (x86)\\Steam\\steamapps\\common', 'Games\\Steam\\steamapps\\common', 'Activision', 'Program Files (x86)\\Activision', 'Program Files\\Activision'):
                roots.append('%s:\\%s' % (d, sub))
        try:
            import winreg
            for hive, key in ((winreg.HKEY_LOCAL_MACHINE, r'SOFTWARE\WOW6432Node\Activision\Call of Duty WAW'), (winreg.HKEY_LOCAL_MACHINE, r'SOFTWARE\Activision\Call of Duty WAW'), (winreg.HKEY_LOCAL_MACHINE, r'SOFTWARE\WOW6432Node\Activision\Call of Duty World at War')):
                try:
                    with winreg.OpenKey(hive, key) as k: roots.append(winreg.QueryValueEx(k, 'InstallPath')[0])
                except OSError: pass
        except ImportError: pass
    found = []
    for r in roots:
        if is_game(r) and r not in found: found.append(r)
        try: names = os.listdir(r)
        except OSError: continue
        for n in names:
            low = n.lower()
            if 'world at war' in low or 'waw' in low or 'call of duty 5' in low or 'cod5' in low:
                p = os.path.join(r, n)
                if is_game(p) and p not in found: found.append(p)
    return found

def browse():
    """Opens the standard Windows 'select folder' window (PowerShell)."""
    ps = ("Add-Type -AssemblyName System.Windows.Forms; $f=New-Object System.Windows.Forms.FolderBrowserDialog; "
          "$f.Description='Select the Call of Duty: World at War folder (the one that contains the zone folder)'; if($f.ShowDialog() -eq 'OK'){$f.SelectedPath}")
    try: return subprocess.run(['powershell', '-NoProfile', '-Command', ps], capture_output=True, text=True).stdout.strip()
    except Exception: return ''

def ask_game(arg=None):
    if is_game(arg): return arg
    games = find_games()
    if len(games) == 1:
        print('Found the game: ' + games[0])
        if input('Use it? [Y/n] ').strip().lower() in ('', 'y', 'yes'): return games[0]
    elif len(games) > 1:
        for i, g in enumerate(games, 1): print('  %d) %s' % (i, g))
        c = input('Choose a number (or press Enter to browse): ').strip()
        if c.isdigit() and 1 <= int(c) <= len(games): return games[int(c) - 1]
    while True:
        print('Select the Call of Duty: World at War folder in the window that opens...')
        p = browse() or input('Or type/paste the folder path here: ').strip().strip('"')
        if is_game(p): return p
        print('That is not the game folder (it must contain the zone and main folders). Try again.')

def main():
    """Opens the window (gui_app.py). Returns True when the window was used; the old console menu stays as a fallback (and with --console)."""
    arg = next((a for a in sys.argv[2:] if not a.startswith('--')), None)
    if '--console' not in sys.argv:
        try:
            import gui_app
            gui_app.run(cod4, find_games, is_game, arg); return True
        except ImportError: pass                       # no Tk on this Python: use the console menu below
        except Exception as e: print('Window failed (%s), using the console menu.' % e)
    print('Call of Duty: World at War - Arabic translation\n  1) Install Arabic\n  2) Restore the original game files')
    c = input('Choose 1 or 2: ').strip()
    g = ask_game(arg)
    if c == '2': cod4.cmd_restore([g])
    else: cod4.cmd_apply([g])
    print('\nDone.')
    return False

if __name__ == '__main__':
    gui = False
    try: gui = main()
    except SystemExit as e:
        if e.code not in (None, 0): print(e.code)
    except Exception as e: print('ERROR:', e)
    if not gui:
        try: input('Press Enter to close...')
        except (EOFError, RuntimeError): pass

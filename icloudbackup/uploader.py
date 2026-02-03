#!/usr/bin/env python3
"""
iCloud Backup App Uploader
"""

import asyncio
import os
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Set, Tuple
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler, FileSystemEvent

import aiohttp
from aiohttp import web
from pyicloud import PyiCloudService

# Constants
BACKUP_DIR = Path("/backup")
COOKIE_PATH = Path("/data/pyicloud/cookie")
FRONTEND_DIR = Path("/app/frontend")
WEB_PORT = 5000
RETRY_DELAY = 60
FOLDER_CREATION_DELAY = 5
FILE_WRITE_DELAY = 5
FILE_STABILITY_CHECK_DELAY = 2
FALLBACK_CHECK_INTERVAL = 300
MAX_FOLDER_RETRIES = 3
SUPERVISOR_API = "http://supervisor"
SUPERVISOR_TOKEN = os.environ.get("SUPERVISOR_TOKEN", "")

# Global variables
verification_code: Optional[str] = None
upload_queue: Optional[asyncio.Queue] = None
processed_files: Set[str] = set()
web_runner: Optional[web.AppRunner] = None
requires_2fa: bool = False
is_authenticated: bool = False


def log(message: str) -> None:
    """Log message with timestamp to stdout."""
    timestamp = datetime.now().strftime("%c")
    print(f"{timestamp}: {message}", flush=True)


def parse_arguments() -> Tuple[str, str, str, bool]:
    """Parse and validate command line arguments."""
    if len(sys.argv) < 5:
        log("Error: Insufficient arguments provided")
        log("Usage: python uploader.py <username> <password> <folder> <delete_after_upload>")
        sys.exit(1)
    
    return (
        sys.argv[1],
        sys.argv[2],
        sys.argv[3],
        sys.argv[4].lower() == "true"
    )


# Web Server Routes
async def serve_index(request: web.Request) -> web.Response:
    """Serve the index.html file."""
    return web.FileResponse(FRONTEND_DIR / 'index.html')


async def serve_static_file(request: web.Request) -> web.Response:
    """Serve static files with fallback to index.html."""
    filename = request.match_info.get('filename', 'index.html')
    file_path = FRONTEND_DIR / filename
    
    if file_path.is_file():
        return web.FileResponse(file_path)
    
    # Fallback for SPA routing
    return web.FileResponse(FRONTEND_DIR / 'index.html')


async def health_check(request: web.Request) -> web.Response:
    """Health check endpoint for Home Assistant."""
    return web.json_response({"status": "ok", "service": "icloud-backup"})


async def status_check(request: web.Request) -> web.Response:
    """Status endpoint for frontend - indicates if 2FA is needed."""
    global requires_2fa, is_authenticated
    
    return web.json_response({
        "requires_2fa": requires_2fa,
        "is_authenticated": is_authenticated,
        "status": "running"
    })


async def receive_code(request: web.Request) -> web.Response:
    """Receive 2FA verification code via POST request."""
    global verification_code
    
    try:
        # Support both form-data and JSON
        if request.content_type == 'application/x-www-form-urlencoded' or 'multipart/form-data' in (request.content_type or ''):
            data = await request.post()
            verification_code = data.get('code')
        else:
            data = await request.json()
            verification_code = data.get('code')
        
        if verification_code:
            log(f"Verification code received: {verification_code}")
            return web.json_response({"success": True, "response": "Code received"})
        
        return web.json_response({"success": False, "error": "No code provided"}, status=400)
            
    except Exception as e:
        log(f"Error receiving verification code: {e}")
        return web.json_response({"success": False, "error": str(e)}, status=400)


async def start_web_server() -> web.AppRunner:
    """Start aiohttp web server for frontend and 2FA code reception."""
    global web_runner
    
    app = web.Application()
    app.router.add_get('/health', health_check)
    app.router.add_get('/status', status_check)
    app.router.add_post('/send_code', receive_code)
    app.router.add_get('/', serve_index)
    app.router.add_get('/{filename:.*}', serve_static_file)
    
    web_runner = web.AppRunner(app)
    await web_runner.setup()
    
    site = web.TCPSite(web_runner, '0.0.0.0', WEB_PORT)
    await site.start()
    
    log(f'Web server running on port {WEB_PORT}')
    return web_runner


# Backup Management
def get_local_backups() -> List[str]:
    """Get list of backup tar files in the backup directory."""
    try:
        return [f.name for f in BACKUP_DIR.iterdir() if f.is_file() and f.suffix == '.tar']
    except Exception as e:
        log(f"Error listing backups: {e}")
        return []


async def verify_file_complete(filepath: Path) -> bool:
    """Verify that a file is completely written by checking size stability."""
    if not filepath.is_file():
        return False
    
    try:
        initial_size = filepath.stat().st_size
        await asyncio.sleep(FILE_STABILITY_CHECK_DELAY)
        
        if not filepath.is_file():
            return False
            
        return filepath.stat().st_size == initial_size
    except Exception as e:
        log(f"Error verifying file {filepath.name}: {e}")
        return False


# iCloud Operations
def connect_to_icloud(username: str, password: str) -> Optional[PyiCloudService]:
    """Establish connection to iCloud with credentials."""
    log('Connecting to iCloud...')
    try:
        return PyiCloudService(username, password, str(COOKIE_PATH))
    except Exception as e:
        log(f'iCloud connection error: {e}')
        return None


def handle_2fa_authentication(api: PyiCloudService) -> bool:
    """Handle 2FA authentication process."""
    global verification_code, requires_2fa, is_authenticated
    
    log('Two-factor authentication required')
    log('Waiting for verification code via web UI...')
    
    # Set flag to indicate 2FA is needed
    requires_2fa = True
    is_authenticated = False
    
    # Wait for code from web interface
    timeout = 300  # 5 minutes timeout
    elapsed = 0
    while verification_code is None and elapsed < timeout:
        time.sleep(1)
        elapsed += 1
    
    if verification_code is None:
        log('Timeout waiting for verification code')
        requires_2fa = False
        return False
    
    try:
        if not api.validate_2fa_code(verification_code):
            log('Invalid verification code')
            verification_code = None
            return False
        
        if not api.is_trusted_session:
            log('Requesting trusted session...')
            if not api.trust_session():
                log('Failed to establish trusted session')
        
        log('2FA authentication successful')
        verification_code = None
        requires_2fa = False
        is_authenticated = True
        return True
        
    except Exception as e:
        log(f'2FA authentication error: {e}')
        verification_code = None
        requires_2fa = False
        return False


def _check_icloud_folder_exists(api: PyiCloudService, folder_name: str) -> bool:
    """Check if the folder exists in iCloud Drive."""
    api.drive[folder_name].dir()
    return True


def _create_icloud_folder(api: PyiCloudService, folder_name: str) -> bool:
    """Create folder in iCloud Drive."""
    api.drive.mkdir(folder_name)
    return True


def _wait_for_folder_visibility(api: PyiCloudService, folder_name: str) -> bool:
    """Wait for created folder to become visible in iCloud Drive."""
    for attempt in range(MAX_FOLDER_RETRIES):
        try:
            api.drive[folder_name].dir()
            return True
        except KeyError:
            if attempt < MAX_FOLDER_RETRIES - 1:
                time.sleep(FOLDER_CREATION_DELAY)
    return False


def ensure_icloud_folder_exists(
    api: PyiCloudService,
    folder_name: str,
    username: str,
    password: str
) -> Tuple[bool, Optional[PyiCloudService]]:
    """Ensure the specified folder exists in iCloud Drive and refresh API if created."""
    try:
        _check_icloud_folder_exists(api, folder_name)
        log(f'Folder "{folder_name}" found')
        return True, api
    except KeyError:
        log(f'Creating folder "{folder_name}"...')
        try:
            _create_icloud_folder(api, folder_name)
            log(f'Folder "{folder_name}" created successfully')

            refreshed_api = connect_to_icloud(username, password)
            if refreshed_api is None:
                log('iCloud reconnection failed after folder creation')
                return False, None
            log('iCloud connection refreshed after folder creation')

            time.sleep(FOLDER_CREATION_DELAY)
            if not _wait_for_folder_visibility(refreshed_api, folder_name):
                log(f'Folder not accessible after {MAX_FOLDER_RETRIES} attempts')
                return False, None

            return True, refreshed_api
        except Exception as e:
            log(f'Failed to create folder: {e}')
            return False, None
    except Exception as e:
        log(f'Error checking iCloud folder: {e}')
        return False, None


def file_exists_in_icloud(api: PyiCloudService, folder_name: str, filename: str) -> bool:
    """Check if a file already exists in iCloud Drive folder."""
    try:
        folder_contents = api.drive[folder_name].dir()

        # folder_contents items can be dicts, objects or simple strings depending on pyicloud version
        for item in folder_contents:
            name: Optional[str] = None

            # dict-like
            if isinstance(item, dict):
                # common keys: 'name', 'filename', 'title'
                name = item.get('name') or item.get('filename') or item.get('title')

            # object-like with attribute
            elif hasattr(item, 'name'):
                try:
                    name = getattr(item, 'name')
                except Exception:
                    name = None

            # plain string
            elif isinstance(item, str):
                name = item

            if name == filename:
                log(f'File already exists in iCloud: {filename}')
                return True

        return False

    except KeyError:
        log(f'Folder "{folder_name}" not found while checking file existence')
        return False
    except Exception as e:
        log(f'Error checking file existence in iCloud: {e}')
        return False


def upload_backup_file(api: PyiCloudService, folder_name: str, backup_file: str) -> bool:
    """Upload a single backup file to iCloud Drive."""
    backup_path = BACKUP_DIR / backup_file
    
    if not backup_path.is_file():
        log(f'File not found: {backup_file}')
        return False
    
    log(f'Uploading: {backup_file}')
    try:
        with open(backup_path, 'rb') as file_in:
            api.drive[folder_name].upload(file_in)
        log(f'Successfully uploaded: {backup_file}')
        return True
    except Exception as e:
        log(f'Upload failed for {backup_file}: {e}')
        return False


def cleanup_local_files(files_to_delete: List[str]) -> None:
    """Delete local backup files after successful upload."""
    for backup_name in files_to_delete:
        try:
            backup_path = BACKUP_DIR / backup_name
            backup_path.unlink()
            log(f'Deleted local file: {backup_name}')
        except Exception as e:
            log(f'Failed to delete {backup_name}: {e}')


# File System Monitoring
class BackupFileHandler(FileSystemEventHandler):
    """Handles file system events for backup directory."""
    
    def __init__(self, queue: asyncio.Queue, loop: asyncio.AbstractEventLoop):
        super().__init__()
        self.queue = queue
        self.loop = loop
        
    def on_created(self, event: FileSystemEvent) -> None:
        """Called when a file is created."""
        if event.is_directory or not event.src_path.endswith('.tar'):
            return
        
        filename = Path(event.src_path).name
        log(f'Backup file detected: {filename}')
        
        asyncio.run_coroutine_threadsafe(
            self.queue.put(filename),
            self.loop
        )


# Home Assistant API Integration
async def check_ha_backups(session: aiohttp.ClientSession) -> List[dict]:
    """Fetch backup list from Home Assistant Supervisor API."""
    if not SUPERVISOR_TOKEN:
        return []
    
    try:
        headers = {
            "Authorization": f"Bearer {SUPERVISOR_TOKEN}",
            "Content-Type": "application/json"
        }
        
        async with session.get(
            f"{SUPERVISOR_API}/backups",
            headers=headers,
            timeout=aiohttp.ClientTimeout(total=10)
        ) as response:
            if response.status == 200:
                data = await response.json()
                return data.get('data', {}).get('backups', [])
            
            log(f'HA API error: HTTP {response.status}')
            return []
                
    except asyncio.TimeoutError:
        log('HA API timeout')
    except Exception as e:
        log(f'HA API error: {e}')
    
    return []


async def monitor_ha_api(queue: asyncio.Queue, interval: int) -> None:
    """Monitor Home Assistant API for new backups."""
    log('Starting HA API monitoring')
    known_backups: Set[str] = set()
    
    async with aiohttp.ClientSession() as session:
        while True:
            try:
                backups = await check_ha_backups(session)
                
                for backup in backups:
                    slug = backup.get('slug', '')
                    
                    if slug and slug not in known_backups:
                        known_backups.add(slug)
                        
                        # Find corresponding tar file
                        matching_files = [f for f in get_local_backups() if slug in f]
                        
                        if matching_files:
                            log(f'New backup detected: {matching_files[0]}')
                            await queue.put(matching_files[0])
                
                await asyncio.sleep(interval)
                
            except Exception as e:
                log(f'HA API monitoring error: {e}')
                await asyncio.sleep(RETRY_DELAY)


# Upload Worker
async def _ensure_connected(
    api: Optional[PyiCloudService],
    username: str,
    password: str
) -> Tuple[Optional[PyiCloudService], Optional[str]]:
    """Ensure iCloud connection exists. Returns (api, error_message)."""
    if api is None:
        api = await asyncio.to_thread(connect_to_icloud, username, password)
        if api is None:
            return None, 'iCloud connection failed, retrying...'
    return api, None


async def _ensure_authenticated(api: PyiCloudService) -> Tuple[bool, Optional[str]]:
    """Ensure iCloud session is authenticated. Returns (ok, error_message)."""
    if api.requires_2fa:
        if not await asyncio.to_thread(handle_2fa_authentication, api):
            return False, '2FA failed, retrying...'
        return True, None

    if api.requires_2sa:
        log('Two-step authentication not supported. Please enable 2FA.')
        sys.exit(1)

    # No 2FA required, mark as authenticated
    global is_authenticated
    is_authenticated = True
    return True, None


async def _ensure_folder(
    api: PyiCloudService,
    folder_name: str,
    username: str,
    password: str
) -> Tuple[Optional[PyiCloudService], Optional[str]]:
    """Ensure iCloud folder exists and return refreshed API if needed."""
    folder_ok, refreshed_api = await asyncio.to_thread(
        ensure_icloud_folder_exists,
        api,
        folder_name,
        username,
        password
    )
    if not folder_ok or refreshed_api is None:
        return api, 'Folder check failed, retrying...'
    return refreshed_api, None


async def _process_backup_file(
    api: Optional[PyiCloudService],
    filename: str,
    username: str,
    password: str,
    folder_name: str,
    delete_after_upload: bool
) -> Tuple[Optional[PyiCloudService], bool, int, Optional[str]]:
    """Process a single backup file. Returns (api, requeue, delay, message)."""
    # Skip if already processed
    if filename in processed_files:
        return api, False, 0, None

    # Wait for file to be fully written
    await asyncio.sleep(FILE_WRITE_DELAY)

    # Verify file exists and is complete
    filepath = BACKUP_DIR / filename
    if not await verify_file_complete(filepath):
        return api, True, 0, f'File incomplete or missing: {filename}, re-queuing'

    log(f'Processing: {filename}')

    # Ensure connection
    api, connection_error = await _ensure_connected(api, username, password)
    if api is None:
        return None, True, RETRY_DELAY, connection_error

    # Ensure authentication
    auth_ok, auth_error = await _ensure_authenticated(api)
    if not auth_ok:
        return api, True, RETRY_DELAY, auth_error

    # Ensure folder exists (refresh API if folder created)
    api, folder_error = await _ensure_folder(api, folder_name, username, password)
    if folder_error:
        return api, True, RETRY_DELAY, folder_error

    # Check if file already exists in iCloud
    if await asyncio.to_thread(file_exists_in_icloud, api, folder_name, filename):
        log(f'Skipping upload - file already exists in iCloud: {filename}')
        processed_files.add(filename)
        return api, False, 0, None

    # Upload file
    if await asyncio.to_thread(upload_backup_file, api, folder_name, filename):
        processed_files.add(filename)

        # Delete local file if configured
        if delete_after_upload:
            await asyncio.to_thread(cleanup_local_files, [filename])
        log(f'Completed: {filename}')
    else:
        log(f'Upload failed: {filename}')

    return api, False, 0, None


async def upload_worker(
    username: str,
    password: str,
    folder_name: str,
    delete_after_upload: bool
) -> None:
    """Process upload queue and handle iCloud uploads."""
    api: Optional[PyiCloudService] = None
    log('Upload worker started')
    
    while True:
        filename = await upload_queue.get()

        try:
            api, requeue, delay, message = await _process_backup_file(
                api,
                filename,
                username,
                password,
                folder_name,
                delete_after_upload
            )

            if requeue:
                if message:
                    log(message)
                await asyncio.sleep(delay)
                await upload_queue.put(filename)

        except Exception as e:
            log(f'Upload worker error: {e}')
            await asyncio.sleep(RETRY_DELAY)
            await upload_queue.put(filename)
        finally:
            upload_queue.task_done()


# Main Application
async def main_async() -> None:
    """Main async execution function."""
    global upload_queue
    
    # Start web server early to make health check available ASAP
    await start_web_server()
    
    # Parse arguments
    username, password, folder_name, delete_after_upload = parse_arguments()
    
    log("=" * 50)
    log("iCloud Backup Uploader")
    log("=" * 50)
    log(f"iCloud folder: {folder_name}")
    log(f"Delete after upload: {delete_after_upload}")
    log("=" * 50)
    
    # Initialize upload queue
    upload_queue = asyncio.Queue()
    
    # Start upload worker
    upload_task = asyncio.create_task(
        upload_worker(username, password, folder_name, delete_after_upload)
    )
    
    # Start filesystem monitoring
    event_loop = asyncio.get_running_loop()
    event_handler = BackupFileHandler(upload_queue, event_loop)
    observer = Observer()
    observer.schedule(event_handler, str(BACKUP_DIR), recursive=False)
    observer.start()
    log(f'Filesystem monitoring active on {BACKUP_DIR}')
    
    # Start HA API monitoring if available
    api_task = None
    if SUPERVISOR_TOKEN:
        api_task = asyncio.create_task(
            monitor_ha_api(upload_queue, FALLBACK_CHECK_INTERVAL)
        )
    
    # Queue existing backups
    existing = get_local_backups()
    if existing:
        log(f'Found {len(existing)} existing backup(s)')
        for backup in existing:
            await upload_queue.put(backup)
    
    # Run until interrupted
    try:
        tasks = [upload_task]
        if api_task:
            tasks.append(api_task)
        
        log("All systems operational - monitoring for backups...")
        # Use gather with return_exceptions to prevent the entire service from crashing
        await asyncio.gather(*tasks, return_exceptions=True)
        
        # If we reach here, a task has unexpectedly completed
        log("WARNING: Background task completed unexpectedly - this should not happen")
        
    except KeyboardInterrupt:
        log("Shutdown requested")
    except Exception as e:
        log(f"Unexpected error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        # Cleanup
        log("Cleaning up...")
        observer.stop()
        observer.join()
        
        if web_runner:
            await web_runner.cleanup()
            log("Web server stopped")


def main() -> None:
    """Main entry point."""
    try:
        asyncio.run(main_async())
    except KeyboardInterrupt:
        log("Interrupted")
        sys.exit(0)


if __name__ == "__main__":
    main()

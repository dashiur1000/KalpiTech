"""Full demonstration against disposable containers; never reads the real .env or CSV."""
import csv
import io
import json
import socket
import subprocess
import sys
import tempfile
import time
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pymysql

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tests/data_import'))
from test_import import ImportTests
from test_auth import Client, TEST_PASSWORD, KALPI_PASSWORD


def free_port():
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        return sock.getsockname()[1]


def encode(rows):
    output = io.StringIO(newline='')
    csv.writer(output).writerows(rows)
    return output.getvalue().encode('utf-8-sig')


def main():
    project = 'kalpitechdemo' + uuid.uuid4().hex[:12]
    with tempfile.TemporaryDirectory(prefix='docker-demo-', dir=ROOT / '.local') as temporary:
        folder = Path(temporary)
        data = folder / 'Data'
        private = folder / 'import'
        data.mkdir()
        private.mkdir()
        stations = encode([['KalpiId','City','Place','Address','KalpiType','PasswordHash'],
                           [1,'עיר הדגמה','א','א','Regular',KALPI_PASSWORD],
                           [2,'עיר הדגמה','ב','ב','Accessible',KALPI_PASSWORD]])
        people = encode([['Id','KalpiId','FirstName','LastName','Voted','EmailAddress','VotedAt','VotedIn'],
                         *[[f'{number:09}',1,'בדיקה','סינתטית','FALSE','','',''] for number in range(1,5)]])
        (data / 'kalpi.csv').write_bytes(stations)
        (private / 'kalpi.csv').write_bytes(stations)
        (data / 'people.csv').write_bytes(people)
        app_port, db_port = free_port(), free_port()
        # Read the actual app compose definition without loading developer secrets.
        env_file = folder / 'test.env'
        env_file.write_text('MYSQL_PASSWORD=SyntheticDbPassword123\nMYSQL_ROOT_PASSWORD=SyntheticRootPassword123\n'
                            'ADMIN_EMAIL=manager@example.test\nADMIN_INITIAL_PASSWORD=' + TEST_PASSWORD + '\n'
                            'MAIL_ENABLED=false\nMAIL_API_KEY=\n', encoding='utf-8')
        config_command = ['docker','compose','--env-file',str(env_file),'-f',str(ROOT / 'compose.yaml'),
                          '-f',str(ROOT / 'compose.app.yaml'),'config','--format','json']
        config = json.loads(subprocess.check_output(config_command, cwd=ROOT))
        config.pop('name', None)
        config['services']['mysql']['ports'] = [{'target':3306,'published':str(db_port),'host_ip':'127.0.0.1','protocol':'tcp'}]
        api = config['services']['api']
        api.pop('build', None)
        api['ports'] = [{'target':8080,'published':str(app_port),'host_ip':'127.0.0.1','protocol':'tcp'}]
        api['volumes'] = [dict(type='volume',source='app_state',target='/workspace/.local'),
                          dict(type='bind',source=str(data),target='/workspace/Data',read_only=True),
                          dict(type='bind',source=str(private),target='/workspace/.local/import',read_only=True)]
        for volume in config['volumes'].values():
            volume.pop('name', None)  # All volumes must belong to our unique project.
        for network in config.get('networks', {}).values():
            network.pop('name', None)
        compose_file = folder / 'compose.json'
        compose_file.write_text(json.dumps(config), encoding='utf-8')
        command = ['docker','compose','-p',project,'-f',str(compose_file)]

        def compose(*args):
            result = subprocess.run([*command,*args], capture_output=True, text=True)
            if result.returncode:
                logs = subprocess.run([*command,'logs','--tail','30','api'],capture_output=True,text=True)
                diagnostic = result.stderr + logs.stdout + logs.stderr
                for secret in ('SyntheticDbPassword123','SyntheticRootPassword123',TEST_PASSWORD,KALPI_PASSWORD):
                    diagnostic = diagnostic.replace(secret, '[redacted]')
                raise AssertionError('Docker operation failed: ' + ' '.join(args) + '\n' + diagnostic)

        def expect(client, path, body=None, status=200):
            actual, payload, _ = client.request(path, body)
            assert actual == status, f'{path}: expected {status}, got {actual}'
            return payload

        connection = None
        try:
            compose('up','-d','--wait','--wait-timeout','180')
            base = f'http://127.0.0.1:{app_port}'
            manager = Client(base)
            assert manager.login()[0] == 200
            assert expect(manager, '/api/election')['state'] == 'Preparation'
            upload_context = SimpleNamespace(client=manager, base=base)
            assert ImportTests.upload(upload_context, files=(stations,people))[0] == 200
            print('PASS: container startup, schema, admin login and Python CSV upload', flush=True)
            regular, accessible = Client(base), Client(base)
            assert regular.login('1', KALPI_PASSWORD)[0] == 200
            assert accessible.login('2', KALPI_PASSWORD)[0] == 200
            expect(regular, '/api/voters/confirm', {'id':'000000001'}, status=409)
            start = datetime.now(timezone.utc) + timedelta(hours=1)
            local = ZoneInfo('Asia/Jerusalem')
            schedule = dict(startsAt=start.astimezone(local).strftime('%Y-%m-%dT%H:%M'),
                            endsAt=(start+timedelta(hours=12)).astimezone(local).strftime('%Y-%m-%dT%H:%M'))
            expect(manager, '/api/election/schedule', schedule)
            connection = pymysql.connect(host='127.0.0.1', port=db_port, user='kalpitech',
                                         password='SyntheticDbPassword123', database='VotesDb',autocommit=True)

            def set_times(age, duration):
                # Only our isolated synthetic DB: reach boundaries without waiting hours.
                now = datetime.now(timezone.utc).replace(tzinfo=None)
                with connection.cursor() as cursor:
                    cursor.execute('UPDATE ElectionSettings SET StartsAt=%s,EndsAt=%s WHERE Id=1',
                                   (now-timedelta(hours=age),now-timedelta(hours=age)+timedelta(hours=duration)))

            set_times(1,12)
            assert expect(manager, '/api/election')['state'] == 'Active'
            expect(manager, '/api/election/schedule', schedule, status=409)
            assert ImportTests.upload(upload_context, files=(stations,people))[0] == 409
            assert expect(regular, '/api/voters/confirm', {'id':'000000001'})['votedIn'] == 1
            duplicate = expect(regular, '/api/voters/confirm', {'id':'000000001'}, status=409)
            assert duplicate['message']
            assert expect(accessible, '/api/voters/confirm', {'id':'000000002'})['votedIn'] == 2
            expect(regular, '/api/envelopes/confirm', {'id':'000000003'}, status=403)
            print('PASS: schedule, activity, import lock, roles, regular/accessible and duplicate votes', flush=True)
            set_times(13,12)
            state = expect(manager, '/api/election')
            assert state['state'] == 'Finished' and state['doubleEnvelopesAllowed']
            expect(regular, '/api/voters/confirm', {'id':'000000003'}, status=409)
            assert expect(manager, '/api/envelopes/confirm', {'id':'000000003'})['votedIn'] == 0
            expect(manager, '/api/envelopes/confirm', {'id':'000000003'}, status=409)
            assert expect(manager, '/api/statistics')['overall']['voted'] == 3
            with connection.cursor() as cursor:
                cursor.execute('SELECT Id,KalpiId,Voted,VotedAt,VotedIn FROM People ORDER BY Id')
                before = cursor.fetchall()
                assert [(row[1],row[2],row[4]) for row in before] == [(1,1,1),(1,1,2),(1,1,0),(1,0,None)]
            set_times(37,12)
            expect(manager, '/api/envelopes/confirm', {'id':'000000004'}, status=409)
            assert ImportTests.upload(upload_context, files=(stations,people))[0] == 409
            print('PASS: post-election envelopes, committee 0000, statistics and 36-hour boundary', flush=True)
            connection.close()
            connection = None
            compose('down')  # Keep only THIS test project's volumes to check persistence.
            compose('up','-d','--wait','--wait-timeout','180')
            assert expect(manager, '/api/statistics')['overall']['voted'] == 3  # Existing cookie still works.
            assert Client(base).login('2',KALPI_PASSWORD)[0] == 200
            connection = pymysql.connect(host='127.0.0.1',port=db_port,user='kalpitech',
                                         password='SyntheticDbPassword123',database='VotesDb',autocommit=True)
            with connection.cursor() as cursor:
                cursor.execute('SELECT Id,KalpiId,Voted,VotedAt,VotedIn FROM People ORDER BY Id')
                assert cursor.fetchall() == before
            # Verify no developer secrets or imported data were copied into the image.
            compose('exec','-T','api','/opt/venv/bin/python','-c',
                    "from pathlib import Path; import os; assert os.getuid()!=0; assert not Path('/workspace/.env').exists()")
            print('PASS: full container recreation preserves votes, uploaded passwords and authentication cookie', flush=True)
        finally:
            if connection:
                connection.close()
            compose('down','--volumes','--remove-orphans')
    print('All Docker demonstration checks passed; temporary containers and volumes removed.', flush=True)


if __name__ == '__main__':
    raise SystemExit(main())

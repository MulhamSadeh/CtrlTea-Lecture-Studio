"""Protected offline administrator invitations; never a public creation API."""
import argparse,os,secrets
from datetime import timedelta
import psycopg
from psycopg.rows import dict_row
from . import accounts as a


def invite(email,recovery=False,reason=''):
    email=a.normalize(email)
    if recovery and len(reason.strip())<10:raise ValueError('An accountable recovery reason is required')
    # An operator must possess the migration/owner DSN; normal runtime/admin
    # browser capabilities cannot invoke this command through an endpoint.
    with psycopg.connect(os.environ['CTRLTEA_MIGRATION_URL'],row_factory=dict_row) as con:
        con.execute("SELECT set_config('ctrltea.auth_service','1',true)")
        con.execute('SELECT pg_advisory_xact_lock(814032604)')
        row=con.execute('SELECT id,email,email_verified_at FROM accounts WHERE normalized_email=%s FOR UPDATE',(email,)).fetchone()
        if not row:raise ValueError('Register the intended owner account first')
        if not row['email_verified_at']:raise ValueError('Verify the intended administrator mailbox first')
        state=con.execute('SELECT completed FROM bootstrap_state WHERE id=1 FOR UPDATE').fetchone()
        if state['completed'] and not recovery:raise ValueError('Initial bootstrap is permanently closed; use audited recovery if needed')
        if recovery:con.execute("UPDATE accounts SET state='active' WHERE id=%s",(row['id'],))
        kind='admin_recovery' if recovery else 'bootstrap'
        token=a.issue(con,row['id'],kind,30)
        con.execute('INSERT INTO security_audit(action,target,outcome,metadata) VALUES(%s,%s,%s,%s)',('operator.'+kind,row['id'],'invited',__import__('json').dumps({'reason':reason[:500]})))
    if not a.deliver(row['id'],row['email'],kind,token):
        raise RuntimeError('Invitation was not delivered; correct the mail provider and issue a fresh invitation')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command',choices=['invite','recover'])
    parser.add_argument('--email',required=True);parser.add_argument('--reason',default='')
    args=parser.parse_args();invite(args.email,args.command=='recover',args.reason)
    print('One-time invitation delivered to the configured mail provider. No token/password is printed.')


if __name__=='__main__':main()

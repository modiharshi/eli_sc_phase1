"""Admin CLI.  python -I -m api.manage create-user NAME ROLE   |   create-api-key LABEL   |   hide / unhide JUDGMENT_ID REASON"""
import getpass
import sys

from . import auth, db

cmd, args = sys.argv[1], sys.argv[2:]
if cmd == "create-user":
    pw = getpass.getpass("password: ") if sys.stdin.isatty() else sys.stdin.readline().strip()
    auth.create_user(args[0], pw, args[1] if len(args) > 1 else "viewer")
    print("created", args[0])
elif cmd == "create-api-key":
    print("API key (shown once):", auth.create_api_key(args[0]))
elif cmd == "hide":
    with db.admin() as c:
        c.execute("insert into judgment_hidden (judgment_id, hidden_by, reason) values (%s, 'cli', %s) on conflict do nothing", (args[0], args[1]))
        c.execute("insert into review_audit (actor, target_table, target_key, action, after_value) values ('cli','judgment',%s,'hide',jsonb_build_object('reason',%s::text))", (args[0], args[1]))
    print("hidden")
elif cmd == "unhide":
    with db.admin() as c:
        c.execute("delete from judgment_hidden where judgment_id = %s", (args[0],))
        c.execute("insert into review_audit (actor, target_table, target_key, action) values ('cli','judgment',%s,'unhide')", (args[0],))
    print("unhidden")
else:
    sys.exit(__doc__)

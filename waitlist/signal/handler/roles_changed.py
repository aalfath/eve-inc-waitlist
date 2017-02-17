from typing import Iterable, Sequence

from waitlist.storage.database import AccountNote, RoleChangeEntry
from waitlist import db
from waitlist.storage.database import Role, Account
from sqlalchemy.sql.expression import or_
from waitlist.signal.signals import roles_changed_sig
from waitlist.data.names import WTMRoles


# noinspection PyUnusedLocal
@roles_changed_sig.connect
def on_roles_changed(sender, to_id: int, by_id: int, added_roles: Sequence[str], removed_roles, note):
    if len(added_roles) <= 0 and len(removed_roles) <= 0 and note == "":
        return
    history_entry = AccountNote(accountID=to_id, byAccountID=by_id, note=note)
    if len(added_roles) > 0:
        db_roles = db.session.query(Role).filter(or_(Role.name == name for name in added_roles)).all()
        for role in db_roles:
            # get role from db
            role_change = RoleChangeEntry(added=True, role=role)
            history_entry.role_changes.append(role_change)
        
    if len(removed_roles) > 0:
        db_roles = db.session.query(Role).filter(or_(Role.name == name for name in removed_roles)).all()
        for role in db_roles:
            role_change = RoleChangeEntry(added=False, role=role)
            history_entry.role_changes.append(role_change)
    db.session.add(history_entry)
    db.session.commit()


# handler to reset welcome mail status
# noinspection PyUnusedLocal
@roles_changed_sig.connect
def on_roles_changed_check_welcome_mail(sender, to_id: int, by_id: int, added_roles: Iterable[str],
                                        removed_roles: Iterable[str], note: str):
    if WTMRoles.tbadge in added_roles or WTMRoles.resident in added_roles:
        acc = db.session.query(Account).get(to_id)
        acc.had_welcome_mail = False

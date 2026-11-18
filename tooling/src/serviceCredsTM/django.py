"""Django adapters; service code supplies API models and financial behavior."""
import hashlib

from django.contrib.auth import get_user_model
from django.contrib.auth.hashers import check_password, make_password
from django.db import connection, transaction
from allauth.account.models import EmailAddress

from .contract import CredentialError


def provision_accounts(service, accounts, *, api_model=None, after_provision=None):
    """Reconcile the fixed managed accounts atomically and serialize startups."""
    accounts = tuple(accounts)
    if len({a.username for a in accounts}) != len(accounts) or len({a.email.lower() for a in accounts}) != len(accounts):
        raise CredentialError("Managed account identities must be distinct")
    publics = [a.public for a in accounts if a.spec.api_key]
    if len(set(publics)) != len(publics):
        raise CredentialError("Managed API public keys must be distinct")
    lock = int.from_bytes(hashlib.sha256(f"service-creds:{service}".encode()).digest()[:8], "big", signed=True)
    User = get_user_model()
    with transaction.atomic():
        with connection.cursor() as cursor:
            cursor.execute("SET LOCAL lock_timeout = '10s'")
            cursor.execute("SELECT pg_advisory_xact_lock(%s)", [lock])
        users = {}
        for account in accounts:
            user = User.objects.filter(username=account.username).first()
            if User.objects.filter(email__iexact=account.email).exclude(pk=user.pk if user else None).exists():
                raise CredentialError(f"Managed account email collision: {account.spec.holder}")
            if EmailAddress.objects.filter(email__iexact=account.email).exclude(user_id=user.pk if user else None).exists():
                raise CredentialError(f"Managed verified email collision: {account.spec.holder}")
            if user is not None and user.email.lower() != account.email.lower():
                # Adopt the existing admin, or reconcile a known owner-bound key;
                # never promote an unrelated username collision into an admin.
                known_owner = account.spec.admin and user.is_superuser
                if account.spec.api_key and api_model is not None:
                    known_owner = known_owner or api_model.objects.filter(public_key=account.public, owner=user).exists()
                if not known_owner:
                    raise CredentialError(f"Managed account username collision: {account.spec.holder}")
            if user is None:
                user = User(username=account.username)
            user.email = account.email
            user.is_active = True
            user.is_staff = account.spec.admin
            user.is_superuser = account.spec.admin
            if account.password is not None:
                if not check_password(account.password, user.password):
                    user.set_password(account.password)
            elif user.has_usable_password():
                user.set_unusable_password()
            user.save()
            if account.spec.password:
                EmailAddress.objects.filter(user=user).exclude(email=account.email).update(primary=False)
                EmailAddress.objects.update_or_create(user=user, email=account.email,
                                                     defaults={"primary": True, "verified": True})
            if account.spec.api_key:
                if api_model is None:
                    raise CredentialError("Service has no managed API adapter")
                key = api_model.objects.filter(public_key=account.public).first()
                if key is not None and key.owner_id != user.pk:
                    raise CredentialError(f"Managed API ownership collision: {account.spec.holder}")
                if key is None:
                    key = api_model(owner=user, public_key=account.public)
                if not check_password(account.secret, key.secret):
                    key.secret = make_password(account.secret)
                key.expires_at = account.expires_at
                key.is_active = True
                key.save()
            users[account.spec.holder] = user
    # Billing/economics own independent durable transactions. Credential
    # reconciliation commits first; a failed financial callback aborts startup
    # and is safely retried under its existing idempotency identity.
    if after_provision is not None:
        after_provision(users)
    return users


def verify_accounts(accounts, cursor, *, api_model=None):
    """Read through the caller's bounded cursor; never lazily upgrade secrets."""
    User = get_user_model()
    quote = connection.ops.quote_name
    for account in accounts:
        columns = ["id", "email", "password", "is_active", "is_staff", "is_superuser"]
        cursor.execute(f"SELECT {', '.join(quote(c) for c in columns)} FROM {quote(User._meta.db_table)} WHERE username = %s",
                       [account.username])
        row = cursor.fetchone()
        if row is None:
            return False
        pk, email, password, active, staff, superuser = row
        if (email != account.email or not active or staff != account.spec.admin or superuser != account.spec.admin):
            return False
        if account.password is not None:
            if not check_password(account.password, password):
                return False
            cursor.execute(f"SELECT 1 FROM {quote(EmailAddress._meta.db_table)} WHERE user_id = %s AND email = %s AND verified AND {quote('primary')}",
                           [pk, account.email])
            if cursor.fetchone() is None:
                return False
        if account.spec.api_key:
            if api_model is None:
                return False
            cursor.execute(f"SELECT owner_id, secret, is_active, expires_at FROM {quote(api_model._meta.db_table)} WHERE public_key = %s",
                           [account.public])
            key = cursor.fetchone()
            if (key is None or key[0] != pk or not key[2] or key[3] != account.expires_at
                    or not check_password(account.secret, key[1])):
                return False
    return True

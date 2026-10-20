"""Compare verified role identities without conflating channel and server."""


CHANNELS = frozenset(('official', 'bilibili', 'unknown'))


def role_channel(role, credentials=None):
    # Grants written before channel support were scoped under 'official'. Keep
    # that storage identity until a new upstream verification supplies metadata.
    channel = role.get('channel', (credentials or {}).get('channel', 'official'))
    return channel if isinstance(channel, str) and channel in CHANNELS else None


def has_verified_role(credentials, role_id, server_id, channel):
    return any(str(role.get('role_id')) == role_id
               and str(role.get('server_id')) == server_id
               and role_channel(role, credentials) == channel
               for role in credentials.get('_verified_roles', []))


def snapshot_generation(credentials, version):
    """Authenticated lower bound of revisions belonging to this snapshot identity."""
    value = credentials.get('_snapshot_generation', version)
    if type(value) is not int or not 1 <= value <= version:
        raise ValueError('Invalid snapshot generation')
    return value


def renewed_snapshot_generation(previous, updated, version):
    """Only unchanged verified identities may keep snapshots across token rotation."""
    def identity(value):
        roles = sorted((str(role.get('role_id')), str(role.get('server_id')),
                        role_channel(role, value)) for role in value.get('_verified_roles', []))
        return (tuple(value.get(key) for key in ('user_id', 'center_uid', 'uid', 'role_id',
                    'server_id', 'channel', '_authorization_id')), roles, value.get('_parent'))
    return snapshot_generation(previous, version) if identity(previous) == identity(updated) else version + 1

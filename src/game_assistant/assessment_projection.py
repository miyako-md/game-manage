"""Read-only assessment augmentation after account scope authorization."""
from dataclasses import replace
from .assessment import assess
from .assessment_defaults import resolve_model
from .assessment_equipped import equipped_configuration
from .wuwa_role_detail import role_detail_data


def with_assessment(snapshot,store,scope,game):
    if snapshot is None or not isinstance(snapshot.payload,dict): return snapshot
    payload=snapshot.payload
    def identity(raw):
        if type(raw) not in (str,int):return None
        value=str(raw).strip()
        if type(raw) is str and raw!=value:return None
        return value if 1<=len(value)<=256 and value.isprintable() else None
    def unknown_identity():
        return dict(status='unscorable',value=None,reason='角色标识未提供或无效',contributions=[],
                    model_version='未知',weight_version='未知',source='equipped_snapshot',formula='未知')
    def score(character):
        return assess(equipped_configuration(game,character,payload,snapshot.fetched_at),resolve_model(store,scope,game,character)[0])
    if game=='nte':
        entries=payload.get('entries',[])
        if not isinstance(entries,list):return snapshot
        # Legacy/malformed rows do not acquire an invented identity or model.
        # Use only actual object rows for equipped lookup while retaining source
        # facts in the returned projection and never changing the input snapshot.
        payload={**payload,'entries':[role for role in entries if isinstance(role,dict)]}
        payload={**payload,'entries':[{**role,'assessment':score(character) if (character:=identity(role.get('id'))) else unknown_identity()}
                                     if isinstance(role,dict) else role for role in entries]}
    else:
        data=role_detail_data(payload)
        role=data.get('role') if data is not None else None
        character=identity(role.get('role_id')) if isinstance(role,dict) else None
        if not character:return replace(snapshot,payload={**payload,'assessment':unknown_identity()})
        # Preserve provenance/envelope for archive consumers; render the inner data.
        enriched={**data,'assessment':score(character)}
        payload={**payload,'data':enriched} if 'data' in payload else enriched
    return replace(snapshot,payload=payload)

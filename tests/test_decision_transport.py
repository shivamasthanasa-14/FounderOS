import json
from founderos.ai_service import _provider_response
from founderos.decision_service import build_context, response_schema, offline_payload, validate_response
from founderos.analytics import load_data
from founderos.config import DATA_DIR
from founderos.dashboard import overview

def test_compact_transport_restores_original_evidence_ids(monkeypatch):
    data=load_data(DATA_DIR); week=sorted(data['team_capacity'].week_start.unique())[-1]
    alert=next(a for a in overview(data,week)['alerts'] if a['area']=='Support')
    context=build_context(data,week,alert); payload=offline_payload(context)
    aliases={fact['id']:f'M{i}' for i,fact in enumerate(context['facts'],1)}
    aliases.update({record['id']:f'R{i}' for i,record in enumerate(context['records'],1)})
    for item in payload['observations']+payload['options']:
        item['evidence_refs']=[aliases[ref] for ref in item['evidence_refs']]
        if 'success_indicators' in item: item['success_indicators']=[aliases[ref] for ref in item['success_indicators']]
    requests=[]; seen=[]
    class Reply:
        def __enter__(self): return self
        def __exit__(self,*args): pass
        def read(self): return json.dumps({'response':json.dumps(payload),'model':'test-double'}).encode()
    def urlopen(request,timeout):
        requests.append(json.loads(request.data))
        assert timeout==1200
        return Reply()
    monkeypatch.setattr('urllib.request.urlopen',urlopen)
    result=_provider_response(context,'Investigate the issue','ollama',schema=response_schema(context),model='test-double',observer=seen.append)
    validate_response(result,context)
    assert result['observations'][0]['evidence_refs'][0].startswith('current.support.')
    assert requests[0]['think'] is False and requests[0]['options']['num_ctx']==4096
    assert 'current.support.backlog' not in json.dumps(requests[0]['format'])
    assert len(seen)==1 and seen[0]['model']=='test-double'

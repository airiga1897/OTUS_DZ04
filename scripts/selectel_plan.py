"""Accept only creation/resumption of the five-VM lab, never changes or deletion."""


def validate_creation(data):
    changes = [r for r in data.get('resource_changes', []) if r['mode'] == 'managed']
    vms = [r for r in changes if r['type'] == 'openstack_compute_instance_v2']
    if len(vms) != 5 or any(not r['type'].startswith('openstack_') or r['change']['actions'] not in (['create'], ['no-op']) for r in changes):
        raise ValueError('План должен содержать пять ВМ и только create/no-op. Изменения, замены и удаления запрещены.')
    return changes

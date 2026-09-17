"""Normalize the planner's BOM contract before the existing library retrieval."""

import re


def normalize_plan(plan):
    if not isinstance(plan, dict) or not isinstance(plan.get('components'), list):
        raise ValueError('planner must return a component list')
    components = []
    used = set()
    for index, component in enumerate(plan['components'], 1):
        if not isinstance(component, dict) or not component.get('search_query'):
            raise ValueError('component lacks a search query')
        value = component.get('uid') or component.get('id')
        prefix = str(component.get('designator_prefix') or 'PART')
        if not re.fullmatch(r'[A-Za-z]+', prefix):
            prefix = 'PART'
        uid = str(value) if value is not None else prefix + str(index)
        if not re.fullmatch(r'[A-Za-z][A-Za-z0-9_]*', uid):
            uid = prefix + str(index)
        quantity = component.get('quantity', 1)
        if isinstance(quantity, bool) or not str(quantity).isdigit() or not 1 <= int(quantity) <= 100:
            raise ValueError('invalid component quantity')
        for copy in range(1, int(quantity) + 1):
            candidate = uid if copy == 1 else f'{uid}_{copy}'
            if candidate in used:
                raise ValueError('duplicate normalized component identifier')
            used.add(candidate)
            parameters = component.get('parameters') or {}
            if not isinstance(parameters, dict):
                raise ValueError('component parameters must be an object')
            components.append({**component, 'uid': candidate, 'quantity': 1,
                               'parameters': parameters, '_source_id': value})
    if not components:
        raise ValueError('empty component preparation')
    return {**plan, 'components': components, '_bom_contract': 'uid-alias-and-quantity-v1'}


def install_contract(legacy):
    def raw_engine_class():
        class RawNetlistEngine(legacy.netlist_module.NetlistEngine):
            cleanup_enabled = False
        return RawNetlistEngine

    legacy._raw_engine_class = raw_engine_class
    factory = legacy.plan_module.create_plan_method

    def create(method):
        planner = factory(method)
        generate = planner.generate_plan

        def normalized(requirement, *, seed=None):
            return normalize_plan(generate(requirement, seed=seed))

        planner.generate_plan = normalized
        return planner

    legacy.plan_module.create_plan_method = create

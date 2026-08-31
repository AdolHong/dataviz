export function parameterDomainFailure(code, message) {
  const error = new Error(`${message} [${code}]`);
  error.code = code;
  return error;
}

export function parameterDomainCanonicalValue(value) {
  if (value == null || typeof value === 'string' || typeof value === 'boolean') return value;
  if (typeof value === 'number') {
    if (!Number.isFinite(value)) {
      throw parameterDomainFailure('invalid_number', 'Parameter Domain values must be finite');
    }
    if (Number.isInteger(value) && !Number.isSafeInteger(value)) {
      throw parameterDomainFailure(
        'unsafe_integer',
        'Parameter Domain integers must be within the exact JavaScript range',
      );
    }
    return value;
  }
  if (Array.isArray(value)) return value.map(parameterDomainCanonicalValue);
  if (typeof value === 'object') {
    return Object.fromEntries(
      Object.keys(value).sort().map(key => [key, parameterDomainCanonicalValue(value[key])]),
    );
  }
  throw parameterDomainFailure(
    'not_json_serializable',
    'Parameter Domain values must be JSON-serializable',
  );
}

export function parameterDomainSignature(value) {
  return JSON.stringify(parameterDomainCanonicalValue(value));
}

export function isEmptyParameterDomainValue(value) {
  return value == null || value === '' || (Array.isArray(value) && value.length === 0);
}

export function projectParameterDomainRelation({
  entry,
  expectedParents,
  values,
  parameterId,
}) {
  if (!entry || !Array.isArray(entry.rows)) {
    throw parameterDomainFailure(
      'parameter_domain_client_projection_missing',
      `Parameter Domain projection is missing consumer ${parameterId}`,
    );
  }
  if (
    parameterDomainSignature([...(entry.parents || [])].sort())
    !== parameterDomainSignature([...expectedParents].sort())
  ) {
    throw parameterDomainFailure(
      'parameter_domain_contract_drift',
      `Parameter Domain projection parents drifted for ${parameterId}`,
    );
  }
  const allowedByParent = Object.fromEntries(expectedParents.map(parentId => {
    const raw = values?.[parentId];
    const candidates = (Array.isArray(raw) ? raw : [raw]).filter(
      value => !isEmptyParameterDomainValue(value),
    );
    return [parentId, new Set(candidates.map(parameterDomainSignature))];
  }));
  if (Object.values(allowedByParent).some(allowed => allowed.size === 0)) return [];

  const projected = new Map();
  for (const row of entry.rows) {
    const parentKeys = Object.keys(row?.parents || {}).sort();
    if (parameterDomainSignature(parentKeys) !== parameterDomainSignature([...expectedParents].sort())) {
      throw parameterDomainFailure(
        'parameter_domain_contract_drift',
        `Parameter Domain relation parents drifted for ${parameterId}`,
      );
    }
    if (!expectedParents.every(parentId => (
      row.parents[parentId] != null && allowedByParent[parentId].has(row.parents[parentId])
    ))) continue;
    const choice = row?.choice;
    const signature = parameterDomainSignature(choice?.value);
    if (signature !== row?.signature) {
      throw parameterDomainFailure(
        'parameter_domain_client_projection_invalid',
        `Parameter Domain candidate signature drifted for ${parameterId}`,
      );
    }
    const previous = projected.get(signature);
    if (previous && parameterDomainSignature(previous) !== parameterDomainSignature(choice)) {
      throw parameterDomainFailure(
        'parameter_domain_metadata_conflict',
        `Parameter Domain maps one value to conflicting metadata for ${parameterId}`,
      );
    }
    if (!previous) projected.set(signature, structuredClone(choice));
  }
  return [...projected.values()];
}

export function initialParameterDomainValue(parameter, choices) {
  const available = choices.filter(choice => !choice.disabled).map(choice => choice.value);
  const policy = parameter.initial || {
    mode:parameter.type === 'multiple_select' ? 'all' : 'first',
  };
  let value;
  if (policy.mode === 'all') value = [...available];
  else if (policy.mode === 'empty') value = parameter.type === 'multiple_select' ? [] : null;
  else if (policy.mode === 'values') value = structuredClone(policy.values || []);
  else if (policy.mode === 'value') value = structuredClone(policy.value);
  else value = available.length ? structuredClone(available[0]) : null;
  if (parameter.required && isEmptyParameterDomainValue(value)) {
    throw parameterDomainFailure(
      'query_parameter_value_required',
      `Query Parameter ${parameter.id} has no available required value`,
    );
  }
  return {
    value,
    intent:parameter.type === 'multiple_select' && policy.mode === 'all'
      ? 'all_available'
      : 'explicit',
  };
}

export function resolveLocalParameterDomainValue(
  parameter,
  choices,
  rawValue,
  intent,
  {preserveUnavailable = false} = {},
) {
  if (preserveUnavailable) {
    return {
      value:structuredClone(rawValue),
      intent:parameter.type === 'multiple_select' && intent === 'all_available'
        ? 'all_available'
        : 'explicit',
    };
  }
  const available = choices.filter(choice => !choice.disabled).map(choice => choice.value);
  const bySignature = new Map(available.map(value => [parameterDomainSignature(value), value]));
  if (parameter.type === 'multiple_select' && intent === 'all_available') {
    return {value:structuredClone(available), intent:'all_available'};
  }
  if (isEmptyParameterDomainValue(rawValue)) {
    return parameter.required
      ? initialParameterDomainValue(parameter, choices)
      : {value:parameter.type === 'multiple_select' ? [] : null, intent:'explicit'};
  }
  const items = parameter.type === 'multiple_select' ? rawValue : [rawValue];
  const retained = items
    .map(value => bySignature.get(parameterDomainSignature(value)))
    .filter(value => value !== undefined);
  if (parameter.type === 'multiple_select') {
    if (items.length && retained.length === 0) return initialParameterDomainValue(parameter, choices);
    return {value:structuredClone(retained), intent:'explicit'};
  }
  return retained.length
    ? {value:structuredClone(retained[0]), intent:'explicit'}
    : initialParameterDomainValue(parameter, choices);
}

export function withUnavailableParameterDomainChoices(parameter, choices, value) {
  const selected = parameter.type === 'multiple_select' ? (value || []) : [value];
  const known = new Set(choices.map(choice => parameterDomainSignature(choice.value)));
  const projected = choices.map(choice => structuredClone(choice));
  for (const item of selected) {
    if (isEmptyParameterDomainValue(item) || known.has(parameterDomainSignature(item))) continue;
    projected.push({
      value:structuredClone(item),
      label:typeof item === 'object' ? parameterDomainSignature(item) : String(item),
      description:'Unavailable in the current Parameter Domain',
      disabled:true,
      unavailable:true,
    });
  }
  return projected;
}

function transform(context) {
  return {
    main: context.table('rows').groupBy('bucket').aggregate({
      count: {field: 'row_id', op: 'count'},
      total: {field: 'measure', op: 'sum'},
      peak: {field: 'row_id', op: 'max'},
    }).sort('bucket').rows(),
  };
}

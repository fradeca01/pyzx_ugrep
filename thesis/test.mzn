array[1..3] of set of int: S = [{1,2}, {2,3}, {5}];

set of int: U = union(i in 1..3)(S[i]);

output [ show(U) ];

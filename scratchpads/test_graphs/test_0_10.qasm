OPENQASM 3.0;
include "stdgates.inc";
qreg q[6];

h q[0];
h q[1];
h q[2];
h q[3];
h q[4];
h q[5];
barrier q;

cz q[0], q[2];
cz q[0], q[5];
cz q[1], q[4];
cz q[1], q[5];
cz q[2], q[4];
barrier q;

x q[5];
y q[2];
z q[0];
z q[3];
z q[4];
s q[1];
s q[2];
s q[3];
s q[4];
h q[0];
h q[1];
h q[2];
h q[4];
h q[5];
s q[0];
s q[4];
s q[5];

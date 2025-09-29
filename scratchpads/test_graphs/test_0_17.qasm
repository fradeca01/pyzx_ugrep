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

cz q[0], q[4];
cz q[1], q[2];
cz q[1], q[5];
cz q[2], q[3];
cz q[2], q[4];
cz q[2], q[5];
cz q[4], q[5];
barrier q;

x q[0];
x q[2];
y q[5];
z q[4];
s q[5];
h q[0];
h q[1];
h q[4];
s q[0];
s q[1];

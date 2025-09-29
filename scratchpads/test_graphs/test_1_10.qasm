OPENQASM 3.0;
include "stdgates.inc";
qreg q[7];

h q[0];
h q[1];
h q[2];
h q[3];
h q[4];
h q[5];
h q[6];
barrier q;

cz q[0], q[1];
cz q[0], q[2];
cz q[0], q[3];
cz q[1], q[4];
cz q[1], q[5];
cz q[2], q[3];
cz q[2], q[4];
cz q[2], q[5];
cz q[2], q[6];
cz q[3], q[4];
barrier q;

x q[4];
x q[5];
z q[1];
z q[3];
z q[6];
s q[2];
s q[3];
s q[6];
h q[1];
h q[2];
s q[1];

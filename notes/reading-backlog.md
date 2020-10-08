# Reading backlog

This note is a dumping point for papers that I might want to put into the literature review.


FUDGE: Fuzz Driver Generation at Scale
https://www.domagoj-babic.com/uploads/Pubs/Fudge/esecfse19fudge.pdf
It's like a fancier ghostwriter for LLVMFuzzOneInput
See also "FuzzGen" - do people at Google actually talk to each other?
https://www.usenix.org/system/files/sec20fall_ispoglou_prepub.pdf

My related work is the ghostwriter
See also also Randoop, Evosuite, https://www.evosuite.org/wp-content/papercite-data/pdf/ase15_faults.pdf


Test data generation by adaptive random testing (section 6)
https://romisatriawahono.net/lecture/rm/survey/software%20engineering/Software%20Testing/Anand%20-%20Automated%20Software%20Test%20Case%20generation%20-%202013.pdf
TLDR; "adaptive random testing" is a whole early-2000s subfield of input generation
where you seek to generate diverse inputs (typically using a distance metric)


TODO: add section on notable PBT tools to literature review
Quickcheck was first
Hedgehog does rose-tree implementation (read up on that)
smallcheck does exhaustive testing
Rudy Matela's thesis for generalisation of failures
link to related ideas in grammar-based fuzzing (by e.g. Andreas Zeller)

model-based stateful testing needs some explication
contrast shrinking/reduction vs normalisation vs generalisation

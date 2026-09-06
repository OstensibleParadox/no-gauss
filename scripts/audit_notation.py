"""Regenerate the notation inventory for this seven-section manuscript; no build."""

from pathlib import Path
import re
import csv
import hashlib
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[1]
FILES = sorted(p for p in (ROOT / 'sections').glob('0[1-7]-*.tex'))
assert len(FILES) == 7
RESULT_RE = re.compile(r'\\begin\{(theorem|lemma|proposition|corollary)\}.*?\\end\{\1\}', re.S)
EQUATION_RE = re.compile(r'\\begin\{(equation\*?|align\*?|gather\*?|multline\*?)\}.*?\\end\{\1\}', re.S)
REF_RE = re.compile(r'\\(?:eqref|[cC]ref|ref)\{([^}]+)\}')
LABEL_RE = re.compile(r'\\label\{([^}]+)\}')

def strip_comments(s):
    return re.sub(r'(?<!\\)%[^\n]*', lambda m: ' ' * len(m.group()), s)

def math_mask(s):
    keep = bytearray(len(s))
    patterns = [r'(?<!\\)\$\$.*?(?<!\\)\$\$', r'(?<!\\)\$(?!\$).*?(?<!\\)\$', r'\\\(.*?\\\)', r'\\\[.*?\\\]']
    spans = [(m.start(), m.end()) for p in patterns for m in re.finditer(p, s, re.S)]
    spans += [(m.start(), m.end()) for m in EQUATION_RE.finditer(s)]
    for a,b in spans: keep[a:b] = b'\x01' * (b-a)
    return ''.join(c if keep[i] or c == '\n' else ' ' for i,c in enumerate(s))

DATA = []
LABELS = {}
for p in FILES:
    raw = p.read_bytes()
    s = strip_comments(raw.decode())
    res = [(m.start(),m.end()) for m in RESULT_RE.finditer(s)]
    math = math_mask(s)
    DATA.append({'path':p, 'source':s, 'math':math, 'results':res, 'sha256':hashlib.sha256(raw).hexdigest()})
    for m in EQUATION_RE.finditer(s):
        for label in LABEL_RE.findall(m.group()):
            LABELS[label] = (p, m.start(), m.end())

REFERENCED = set()
for source_index,d in enumerate(DATA,1):
    for a,b in d['results']:
        for group in REF_RE.findall(d['source'][a:b]):
            for label in group.split(','):
                if label.strip() in LABELS:
                    REFERENCED.add((source_index,*LABELS[label.strip()]))

def overlap(a,b,spans):
    return any(a >= x and b <= y for x,y in spans)

def first_find(snippet, file_index=None):
    for i,d in enumerate(DATA,1):
        if file_index and i != file_index: continue
        pos=d['source'].find(snippet)
        if pos >= 0:
            return str(d['path'].relative_to(ROOT))+':'+str(d['source'][:pos].count('\n')+1)
    return 'not-found-in-snapshot'

ROWS=[]
def add(key, kind, scope, pattern, expansion, definition, decision='retain', notes='', math_only=True, allowed=None, flags=0):
    matches=[]; direct=[]; referenced=[]
    allowed = set(range(1,8)) if allowed is None else allowed
    # A TeX single-letter subscript ends after that letter, even when the
    # following multiplicative factor is adjacent in source (S_AS_B, Pi_kD).
    if kind=='notation' and '_' in pattern:
        pattern=pattern.replace(r'(?![A-Za-z])','')
    for i,d in enumerate(DATA,1):
        if allowed and i not in allowed: continue
        source=d['math'] if math_only else d['source']
        for m in re.finditer(pattern,source,flags):
            line=d['source'][:m.start()].count('\n')+1
            # The Fourier p,q,r family is only bound in the Fourier construction
            # and in the orthogonal reuse before the rigidity argument.
            if key=='p,q,r' and i==5 and line>=195: continue
            if key=='p,q,r' and i==7 and line>=155: continue
            if key in ('L_a and widehat L_a','countable carrier D') and (i!=4 or line>=114): continue
            location=str(d['path'].relative_to(ROOT))+':'+str(line)
            item=(location,m.group())
            matches.append(item)
            if overlap(m.start(),m.end(),d['results']): direct.append(item)
            elif any(origin in allowed and p==d['path'] and m.start()>=a and m.end()<=b for origin,p,a,b in REFERENCED): referenced.append(item)
    total=len(matches); direct_n=len(direct); reference_n=len(referenced)
    if kind=='removed': status='removed; zero expected'
    elif scope.startswith('proof-local') or scope.startswith('local-parameter'):
        status='scoped binder; not promoted to manuscript terminology'
    elif scope.startswith('descriptive'):
        status='descriptive phrase; no independent exported symbol'
    elif total<3: status='FLAG: fewer than 3 lexical uses'
    elif direct_n: status='load-bearing: >=3 uses and direct result occurrence'
    elif reference_n: status='contextual: result refers to defining/assumption equation'
    else: status='FLAG: no result occurrence'
    ROWS.append([key,kind,scope,pattern,total,direct_n,reference_n,matches[0][0] if matches else '',definition,expansion,status,decision,notes,'; '.join(dict.fromkeys(x[0] for x in direct)),','.join(f'{i:02d}' for i in sorted(allowed))])

single=lambda x: r'(?<![A-Za-z\\])'+x+r'(?![A-Za-z_])'
add(r'\rho','notation','manuscript',r'\\rho(?![A-Za-z])','Law(X), the common coordinate probability law',first_find(r'Let \(X\) have a centered probability law'))
add(r'\mu','notation','manuscript',r'\\mu(?![A-Za-z_])',r'default rho^{tensor N} on R^N; explicitly rebound to a general reference product/measure in section07 block and marginal theorems',first_find(r'\mu=\rho^{\otimes\N}'))
add(r'\mu_n','notation','manuscript',r'\\mu_(?:n|N)(?![A-Za-z])',r'first n marginal of mu; equals rho^{tensor n} in the i.i.d. setting',first_find(r'\mu_n=\rho^{\otimes n}'))
add(r'\phi','notation','manuscript',r'\\phi(?![A-Za-z_])',r'u -> E exp(iuX)',first_find(r'and characteristic function \(\phi'))
add('R','notation','manuscript',single('R'),r'eta phi_prime(xi) phi(eta) - xi phi(xi) phi_prime(eta)',first_find(r'R(\xi,\eta)='),notes=r'Bare R excludes \R and indexed proof-local projections; law stays fixed except explicit examples.')
add(r'W_{\xi,\eta}','notation','manuscript',r'W_\{\\xi,\\eta\}',r'(exp(i xi x)-phi(xi))(exp(i eta y)-phi(eta))',first_find(r'W_{\xi,\eta}(x,y)'))
add(r'O_\theta','notation','manuscript',r'O_\\theta',r'[[cos theta,-sin theta],[sin theta,cos theta]]',first_find(r'O_\theta='))
add('H','notation','manuscript',single('H'),r'ell^2(N;R), coefficient Hilbert space, not sample space',first_find(r'Put \(H='),notes='H_A belongs to a separate subscripted family.')
add(r'\mathcal B(H)','notation','standard operator space',r'\\mathcal B\(H\)','bounded linear operators on H',first_find(r'\mathcal B(H)'))
add(r'\GL','notation','standard operator group',r'\\GL(?![A-Za-z])','bounded invertible operators, or invertible real matrices with the displayed domain',first_find(r'\GL(H)'))
add(r'\mathcal P','notation','manuscript',r'\\mathcal P(?![A-Za-z_])','coordinate permutations with each coordinate sign preserving rho',first_find(r'\mathcal P=\{Q'))
add(r'\Phi_T family','notation','manuscript',r'\\Phi_(?:[A-Za-z]|\{)','measurable row-series realization of the subscripted bounded operator',first_find(r'let \(\Phi_T\)'))
add(r'\nu_T family','notation','manuscript',r'\\nu_(?:[A-Z]|\{(?=[A-Z]))',r'(Phi_T)_# mu for the subscripted bounded operator',first_find(r'Write \(\nu_T='),notes='Excludes nu_a and nu_s used for Lebesgue decomposition.')
add(r'\Aff','notation','manuscript',r'\\Aff(?![A-Za-z])',r'int sqrt((d lambda/dm)(d nu/dm)) dm',first_find(r'\Aff(\lambda,\nu)'))
add('h','notation','manuscript',single('h'),r'h(lambda,nu)^2=2-2 Aff(lambda,nu)',first_find(r'h(\lambda,\nu)^2='),notes='Single-letter count includes scoped test-function h in Fourier dual proof; locations disambiguate; Hellinger result occurrences are independently visible.')
add('P_n family','notation','manuscript',r'(?<!\\mathcal )P_(?:n|m|N)(?![A-Za-z])','orthogonal projection in H onto the indicated initial coordinate segment',first_find(r'Let \(P_n:H\to H\)'),notes='Excludes mathcal P_n; capital N and m denote the same projection family at a different size.')
add(r'\pi_n','notation','manuscript',r'\\pi_n(?![A-Za-z])',r'coordinate extraction R^N -> R^n',first_find(r'\(\pi_n:\R^{\N}\to\R^n\)'))
add('E_n(T)','notation','manuscript',r'E_(?:n|N)(?![A-Za-z])',r'-2 log Aff(mu_n,(pi_n)_# nu_T)',first_find(r'E_n(T)='))
add(r'\mathcal S_2','notation','standard operator ideal',r'\\mathcal S_2','Hilbert-Schmidt operators; finite-dimensional norm equals Frobenius norm',first_find(r'Write \(\mathcal S_2(H)'))
add('f','notation','manuscript',single('f'),'density of rho when rho is absolutely continuous',first_find(r'Suppose \(\rho(dx)=f(x)\,dx\)'))
add('g','notation','manuscript',single('g'),'sqrt(f)',first_find(r'put \(g=\sqrt f\)'))
add('s','notation','manuscript',single('s'),r'-f_prime/f=-2g_prime/g almost everywhere under positive-density assumptions',first_find(r'Define the location score'),notes='Legacy s,t frequency binders are excluded only where renamed in source; inspect first-use locations if this count changes.')
add('J','notation','manuscript',single('J'),r'E[s(X)^2]=4||g_prime||_2^2',first_find(r'J:='))
add('d','notation','manuscript',r'(?<![A-Za-z\\])d(?![A-Za-z_\\])',r'x s(x)-1',first_find(r'd(x):='),notes='Excludes d_n and d\\mu; scope is scale-score formulas and their arguments; TeX dx with no separator is excluded.')
add(r'\kappa','notation','manuscript',r'\\kappa(?![A-Za-z])',r'E[d(X)^2]=4||xg_prime||_2^2-1',first_find(r'\kappa:='))
add('S_A family','notation','manuscript',r'S_[AB](?![A-Za-z])',r'sum A_ij(s(X_i) X_j-delta_ij), matrix score',first_find(r'S_A(\mathbf X)='))
add(r'\mathcal I','notation','manuscript',r'\\mathcal I(?![A-Za-z])',r'<A,I B>_F=E[S_A S_B], Fisher operator; scalar form is the pairing',first_find(r'define the matrix Fisher operator'))
add('C_f','notation','manuscript',r'C_f(?![A-Za-z])',r'max(kappa,J+1), Fisher upper constant',first_find(r'C_f:='))
add('U_A family','notation','manuscript',r'U_(?:[AB]|\{(?:[AB]|\\exp))',r'(U_A v)(y)=abs(det A)^(-1/2)v(A^(-1)y)',first_find(r'(U_Av)(y)='),notes='Excludes U_n used as a local orthogonal-approximation sequence.')
add(r'\Omega_n','notation','manuscript',r'\\Omega_n(?![A-Za-z])',r'product_i g(x_i), square root density of mu_n',first_find(r'\Omega_n(x)='))
add('G_A family','notation','manuscript',r'G_(?:[AB]|\{[AB])',r'-(tr A)v/2-(Ax) dot grad v, generator of U_exp(tA)',first_find(r'G_Av='))
add('p,q,r','notation','manuscript with explicit local construction',r'(?<![A-Za-z\\])[pqr](?![A-Za-z_])','centered finite real Fourier sums with the displayed score/coordinate dual moments',first_find(r'There exist centered finite real Fourier sums'),allowed={3,5,7},notes='Count section03 and its early orthogonal/zero-density reuse in sections05/07; later local block densities and scalars are excluded.')
add('H_A family','notation','manuscript',r'H_[AB](?![A-Za-z])',r'sum_i A_ii r(X_i)+sum_(i!=j) A_ij p(X_i)q(X_j)',first_find(r'H_A(\mathbf X):='))
add('C_0','notation','local-parameter of Fourier-function lemma',r'C_0(?![A-Za-z])','constant in ||H_A||_2 <= C_0 ||A||_F',first_find(r'\le C_0\|A\|_F'),notes='In section05 globalization C_0 is rebound as the local Hellinger upper constant; the scopes are distinct, not a global constant identity.')
add('C_1','notation','local-parameter of generator lemma',r'C_1(?![A-Za-z])','constant in ||G_B(H_A Omega_n)||_2 <= C_1||A||_F||B||_F',first_find(r'constant $C_1$'))
add(r'\mathcal P_n','notation','manuscript',r'\\mathcal P_n(?![A-Za-z])','allowed signed-permutation matrices of dimension n',first_find(r'Let \(\mathcal P_n\)'))
add('d_n','notation','manuscript',r'd_n(?![A-Za-z])',r'min_(Q in P_n)||T-Q||_F',first_find(r'd_n(T)='))
add(r'\mathcal F_n family','notation','manuscript',r'\\mathcal F_(?:n|N)(?![A-Za-z])','sigma-field generated by the first n sample coordinates',first_find(r'\mathcal F_n=\sigma'))
add(r'\ell_n family','notation','manuscript',r'\\ell_(?:n|N)(?![A-Za-z])','finite-marginal density ratio evaluated on pi_n x; in a proof with generic nu the same conditional-density construction',first_find(r'\ell_n(x)='))
add('Z_T','notation','manuscript',r'Z_T(?![A-Za-z])','d nu_T/d mu on the equivalence branch',first_find(r'with density \(Z_T\)'))
add('C_lambda','notation','local-parameter of realization lemma',r'C_\\lambda','second-moment domination constant for the law lambda',first_find(r'C_\lambda\|a\|_2^2'))
add(r'\Gamma','notation','local-parameter of realization lemma',r'\\Gamma(?![A-Za-z])','a fixed countable subgroup of GL(H)',first_find(r'fixed countable subgroup \(\Gamma'),allowed={4},notes='The ordinary Gamma function in section07 is a separate standard function and is not counted as this group parameter.')
add('countable carrier D','notation','local-parameter of realization lemma',single('D'),'common full-measure Borel invariant carrier for the fixed countable group',first_find(r'Borel set \(D'),allowed={4})
add('L_a and widehat L_a','notation','proof-local construction',r'(?:\\widehat )?L_a','L2 row sum and its Borel subsequence version for a fixed coefficient vector a',first_find(r'limit \(L_a\)'),allowed={4},notes='Proof construction; no exported theorem terminology is attached to the two representatives.')
add(r'\mathcal A','notation','proof-local translation group',r'\\mathcal A(?![A-Za-z])','countable group generated by rational e_j and T e_j translations',first_find(r'Let \(\mathcal A\)'))
add('D_a and Q_M','notation','proof-local contraction shorthand',r'(?:D_[a-z]|D_\{\\mathbf [a-z]\}|Q_[A-Z](?:_0)?)','linear and off-diagonal quadratic coordinate sums explicitly defined inside generator proof',first_find(r'D_a(u)='),notes='Local algebraic abbreviations avoid unreadable repeated sums; not introduced as named manuscript concepts.')
add('F(M,B;...)','notation','proof-local contraction shorthand',r'(?<![A-Za-z\\])F\(','explicit three-index derivative sum in the generator proof',first_find('F(M,B;'),allowed={3})
add(r'\Pi_k','notation','proof-local output-block projection',r'\\Pi_k(?![A-Za-z])','projection onto kth output block in globalization proof',first_find(r'Let \(\Pi_k\)'),notes='Renamed from R_k to keep the bare-letter family R associated with the rotational Fourier defect.')

terms=[
 ('rotational Fourier defect','manuscript','R, explicitly defined by the two-frequency derivative identity'),
 ('centered Fourier feature','manuscript','the explicit bounded function W_{xi,eta}'),
 ('weighted Fourier jet','descriptive curve only','explicit curve u -> (u phi(u),phi_prime(u)); no Gamma symbol retained'),
 ('matrix Fisher operator','manuscript','the operator mathcal I defined by the score covariance pairing'),
 ('finite real Fourier sums','manuscript','finite real linear combinations of 1, cos(xi x), sin(xi x)'),
 ('location score','descriptive role of s','-f_prime/f for the location family; no additional abstract object beyond s'),
 ('scale score','descriptive role of d','x s(x)-1 for the scale family; no additional abstract object beyond d'),
 ('matrix score','descriptive role of S_A','the explicitly displayed matrix-path density derivative'),
 ('projected Hellinger energy','manuscript','E_n(T), with actual output marginals'),
 ('finite-marginal likelihood ratios','manuscript','the family ell_n and its explicitly stated reciprocals'),
 ('exact linear stabilizer','descriptive group role','operators satisfying nu_T=mu; identified with mathcal P'),
 ('half-density pairing','descriptive formula only','the displayed integral of H_A against square-root densities'),
 ('local Hellinger coercivity','manuscript','the two-sided Frobenius/Hellinger estimate near identity'),
 ('global Hellinger coercivity','manuscript','the dimension-free estimate using d_n modulo allowed permutations'),
 ('location Fisher information','descriptive standard quantity','finite ||g_prime||_2^2, equivalently finite J'),
 ('scale Fisher information','descriptive standard quantity','finite ||xg_prime||_2^2, equivalently finite kappa'),
]
for phrase,scope,meaning in terms:
    pattern=re.escape(phrase).replace(r'\ ',r'\s+')
    if phrase=='projected Hellinger energy': pattern=pattern.replace('energy',r'energ(?:y|ies)')
    if phrase=='finite-marginal likelihood ratios': pattern=pattern[:-1]+'s?'
    add(phrase,'terminology',scope,pattern,meaning,first_find(phrase),math_only=False,flags=re.I,
        decision='retain as explicit description' if scope.startswith('descriptive') else 'retain canonical phrase',
        notes='Case-insensitive whitespace-normalized phrase count; headings are included. Descriptive roles are not asserted to pass the exported-term threshold.' if scope.startswith('descriptive') else 'Case-insensitive whitespace-normalized phrase count; headings are included.')

for symbol,pattern,reason in [
 (r'R_\mu',r'R_\\mu','mu is the infinite product, not the coordinate law; simplified to R'),
 (r'\Gamma_\mu',r'\\Gamma_\\mu','never needed in a proposition; explicit curve replaces the named symbol'),
 (r'\mathcal R_w',r'\\mathcal R_w','one-off scalar frequency integral is displayed without a named energy'),
 ('Fourier curvature',r'Fourier\s+curvature','unused geometric synonym removed'),
 ('weighted jet alias',r'weighted(?:-|\s+)jet','canonical descriptive phrase is weighted Fourier jet'),
 (r'G_{\xi,\eta}',r'G_\{\\xi,\\eta\}','direct derivative of expected W replaces response-function alias; G_A reserved for generator'),
 (r'\mathscr I_f^{(n)}',r'\\mathscr I','single named Fisher operator replaces the extra glyph'),
 (r'\mathcal I_f^{(n)}',r'\\mathcal I_f','law/dimension are fixed in scope; scalar form expanded as a pairing'),
 (r'\lambda_f',r'\\lambda_f','one-off minimum expanded as min(kappa,J-1)'),
 (r'\mathcal R_A',r'\\mathcal R_A','one-off remainder replaced by explicit difference bound'),
 ('D_Y/R_X/R_Y aliases',r'(?:D_Y|R_X|R_Y)','affine normalization directly displays the marginal correction'),
 (r'\Sigma_f',r'\\Sigma_f','allowed coordinate signs displayed directly in group definition'),
 (r'\mathcal P_f',r'\\mathcal P_f','rho fixed in scope; canonical group mathcal P'),
 ('d_{n,f}',r'd_\{n,f\}','fixed-law index removed; canonical distance d_n'),
]:
    add(symbol,'removed','removed',pattern,reason,'removed in this edit',decision='replaced by explicit description or canonical notation',math_only=False,flags=re.I if 'alias' in symbol or 'curvature' in symbol else 0)

add(r'\mathcal G_\rho','notation','manuscript section07',r'\\mathcal G_\\rho',r'{T in GL(H): nu_T equivalent to mu}; characterized by Hilbert-Schmidt matching and the row support tests for T and T^(-1)',first_find(r'\mathcal G_\rho',7),allowed={7},notes='Selected section07 inventory only; theorem proof separately reviewed by the root and another agent.')
add(r'\mathcal U','notation','manuscript section07',r'\\mathcal U(?![A-Za-z])',r'{x in R:f(x)>0}, defined up to the density representative; row laws have densities so null-set changes do not alter the tests',first_find(r'\mathcal U=\{x',7),allowed={7})
add(r'\rho^-','notation','manuscript section07',r'\\rho\^-',r'Law(-X)',first_find(r'\rho^-=\Law(-X)',7),allowed={7})
add('r_k','notation','manuscript section07',r'r_k(?![A-Za-z])',r'Aff(lambda_k,eta_k), block affinity',first_find(r'r_k=\Aff',7),allowed={7})
add('L (block affinity sum)','notation','manuscript section07',single('L'),r'sum_k -log r_k',first_find(r'L=\sum_k',7),allowed={7},notes='Scoped to the block-product theorem and its corollary; unrelated cutoff L in original6 is excluded.')
add('a_k,b_k','notation','manuscript section07',r'(?:(?<![A-Za-z\\])|(?<=_k))[ab]_k',r'a_k=lambda_k({q_k>0}), b_k=eta_k({p_k>0}); common-support masses',first_find(r'a_k=\lambda_k',7),allowed={7},notes='The corollary states products of these masses as the masses of the absolutely continuous parts. Regex recognizes adjacent TeX factors in prod_kb_k and a_kb_k.')
add('D_n(M)','notation','manuscript section07',r'D_n(?![A-Za-z])','sum of forward and reverse finite-marginal likelihood-ratio tail integrals above M',first_find(r'D_n(M)=',7),allowed={7})
add(r'\lambda_k,\eta_k','notation','local-parameter of block-product theorem',r'\\(?:lambda|eta)_k','reference and comparison block probability measures',first_find(r'\lambda_k\)',7),allowed={7})
add('p_k,q_k,m_k','notation','local-parameter of common-mass corollary',r'(?<![A-Za-z\\])[pqm]_k','m_k=(lambda_k+eta_k)/2; p_k=d lambda_k/dm_k and q_k=d eta_k/dm_k',first_find(r'Take \(m_k=',7),allowed={7},notes='These local densities do not replace the Fourier functions p,q.')
add('p_n,q_n,m_n','notation','local-parameter of marginal-tail proposition',r'(?<![A-Za-z\\])[pqm]_n','a common dominating measure for the nth marginals and their two densities',first_find(r'Choose densities \(p_n,q_n\)',7),allowed={7})
add(r'\delta_k','notation','local-parameter of block-rotation examples',r'\\delta_k','distance of theta_k from a multiple of pi/2, in [0,pi/4]',first_find(r'\delta_k=\min',7),allowed={7})
add('f_c','notation','local-parameter of scaling example',r'f_c','rescaled scalar density c^(-1)f(y/c)',first_find(r'f_c(y)=',7),allowed={7})

for row in ROWS:
    if row[0]=='projected Hellinger energy':
        row[11]='resolved: concept is carried by the defined symbol E_n in result statements'
        row[12]+=' Literal phrase flag retained; semantic statement use is supplied by expanding E_n.'
    elif row[0] in ('local Hellinger coercivity','global Hellinger coercivity'):
        row[11]='resolved: local/global are descriptive qualifiers, not separate exported terms'
        row[12]+=' Literal phrase flag retained; no artificial repetitions were added.'

out=ROOT/'audit'
out.mkdir(exist_ok=True)
with (out/'notation-review.tsv').open('w',newline='') as f:
    writer=csv.writer(f,delimiter='\t')
    writer.writerow(['object_or_phrase','kind','scope','python_regex','total_lexical_occurrences_in_count_scope','direct_result_occurrences','additional_occurrences_in_result_referenced_equations','first_counted_occurrence','definition_or_binding','semantic_expansion','burden_assessment','decision','limits_or_notes','direct_result_locations','counted_sections'])
    writer.writerows(ROWS)

hashes='\n'.join(str(d['path'].relative_to(ROOT))+'  '+d['sha256'] for d in DATA)
flags='\n'.join('- '+r[0]+': '+r[10]+' (total='+str(r[4])+', direct='+str(r[5])+', referenced='+str(r[6])+')' for r in ROWS if r[10].startswith('FLAG')) or 'No automatically flagged exported object in this snapshot.'
text='''SOURCE AND NOTATION REVIEW: ALL SEVEN SECTIONS

Scope
This source audit inventories all seven included sections at the snapshot listed below. Manuscript-scoped rows count all seven sections; explicitly local families use the smaller scope recorded in counted_sections. The new seventh-section rows cover the exact equivalence group, positivity set, reflected law, block affinities and their logarithmic sum, common-support masses, marginal ratio tails, and their local densities and example parameters. The detailed semantic review below was performed for sections01--06; a focused definition-expansion check of the seventh-section group and tail criteria is also recorded. The separate seventh-section proof review and the root's integration review supplement these source checks. This audit does not claim machine verification of theorem truth.

Method and limitations
notation-review.tsv gives deterministic lexical occurrence counts for named object families and canonical phrases. The mathematical-token rows are counted inside TeX math delimiters and equation/align/gather/multline environments. Command occurrences in implicitly mathematical table columns may therefore be omitted. TeX one-letter subscripts are recognized even when the next factor is adjacent in source, such as S_AS_B or prod_kb_k. Plain one-letter variables can still be undercounted in compact products such as xs(x); these are regex counts, not a full TeX parse. Phrase rows are case-insensitive, permit whitespace variation, and include titles/headings. Labels, references, and comments are not treated as substantive uses. A match may cross a source line; its reported location is the first line.

A direct result occurrence lies in a theorem, proposition, lemma, or corollary environment, excluding its subsequent proof. An additional referenced-equation occurrence lies outside those environments in an equation explicitly referenced from a result statement in the counted sections. Each equation location is counted once, even if several results reference it. This column discloses contextual dependence; it does not pretend that an absent symbol was printed in the statement itself.

The >=3/appears-in-a-result test is applied to exported named objects. A notation family is grouped by its declared role, not by arbitrary reuse of an alphabetic character. Local proof binders (coefficient vectors, cutoff sizes, temporary matrix factors, row-sum representatives, contraction sums, and local constants) remain scoped to the calculation. They are not promoted to persistent manuscript terminology. This is an explicit scope distinction, not a claim that every local dummy variable literally meets the user's threshold. Descriptive standard phrases attached directly to a formula are recorded separately and are not asserted to pass an exported-term threshold merely because a related symbol does.

Counts can flag candidates; they cannot prove mathematical statements true, detect every semantic collision, or certify all possible substitutions. The semantic checks below were read against their definitions and hypotheses by an independent reviewer. No compilation, PDF rendering, theorem prover, or numerical experiment was run.

Semantic definition-expansion checks
1. rho is the coordinate law, mu=rho^(tensor N) is a measure on the product Borel space R^N, and mu_n=rho^(tensor n) is the finite product. A product sample is not asserted to lie in H=ell^2. Introducing rho also makes the moment-only stabilizer independent of the existence of a density f.
2. P_n:H->H and pi_n:R^N->R^n now have distinct domains. P_n K P_n remains a finite-rank operator compression; (pi_n)_#nu_T is an actual output marginal. Expanding E_n(T) uses the latter and never a principal matrix-corner law.
3. Phi_T is defined for bounded operators and gives Borel versions of row sums. Its common pointwise action is asserted only on each fixed countable operator group. nu_T always expands to (Phi_T)_#mu. The construction uses a covariance/second-moment domination bound and selected subsequences, rather than asserting ordinary partial-sum convergence under every correlated orbit law.
4. The rotational Fourier defect R is the displayed antisymmetric two-frequency expression. The bounded object is W_(xi,eta), not R over the whole frequency plane. Its expected rotational derivative is displayed directly; the unused function G_(xi,eta) was removed, leaving G_A for the unitary-representation generator. The sign agrees with the displayed orientation of O_theta.
5. The determinant of the explicit weighted Fourier curve equals -R. No independent Gamma symbol or Fourier-curvature invariant is required. The narrative retains the curve description; it does not introduce another theorem parameter. The statement about the unweighted curve was restricted to nondegenerate Gaussians.
6. The affine-normalization formula expands the mean-corrected derivative. Its marginal correction im(a-b)phi_Y(a)phi_Y(b) remains present. Eliminating D_Y and R_Y did not discard this term. The coordinate law changes only where Y and its standardized law are explicitly introduced.
7. The sole Fisher operator I is defined by <A,I B>_F=E[S_A S_B]. Its explicit action JA+A*+(kappa-J-1)diag A expands to the same diagonal, symmetric off-diagonal, and skew-symmetric contributions as the quadratic formula. The operator and its scalar quadratic form no longer use competing glyphs. diag acts on matrices; vectors of diagonal entries are bound separately where needed.
8. U_A is the unitary action on square-root densities, Omega_n is the product square-root density, and G_A is its generator. The existing path lemma now states the L2 derivative identity that was previously used only inside its proof. This gives the notation substantive statement content without adding artificial repetitions.
9. H_A is the explicit sum built from p,q,r. Its L2 bound is under mu_n. Its generator bound is a separate estimate. The prose retains the limitation that an arbitrary mixed output law need not have the same dimension-free variance bound. The global local-to-stabilizer reduction uses right multiplication, not conjugation.
10. ell_n(x) is the Radon-Nikodym density of the nth output marginal evaluated at pi_n x, so it is a random variable on the common infinite product space. Its reciprocal is the reverse marginal density under nu_T. The source index typo sup_N E_n(T) was corrected to sup_n E_n(T).
11. The translation dichotomy now precedes the marginal-likelihood criterion that invokes it. Rational translations in input coordinates and their T images generate a fixed countable group. Quasi-invariance plus ergodicity is used to upgrade positive affinity to equivalence under the stated positive-density/Sobolev assumptions. The statement is not exported to arbitrary support laws without those hypotheses.
12. The introductory claim about detecting all infinitesimal matrix directions is explicitly qualified by the subsequent moment and Sobolev assumptions. The single-coordinate Gaussian characterization itself needs only centering and a first moment. The full matrix bounds retain the second-moment and scale regularity requirements; the orthogonal refinement uses only location regularity.
13. In section07, mathcal U means {f>0}, not the closed support. The operator conditions test actual zero-set avoidance by every row of T and of T^(-1). The source explains why changing the density on a Lebesgue-null set leaves the conditions unchanged: every nonzero row sum has an absolutely continuous scalar law.
14. mathcal G_rho is defined as {T:nu_T equivalent to mu}. The displayed replacement is the Hilbert-Schmidt matching condition together with both forward and inverse row tests. The inverse identity T^(-1)-Q^(-1)=-T^(-1)(T-Q)Q^(-1) preserves the ideal condition; measurable composition supplies the stated group operation. The orthogonal version substitutes T*=T^(-1) and retains its location-only regularity scope.
15. rho^- denotes Law(-X). The support classification distinguishes equality rho^-=rho, equivalence without equality, and failure of equivalence. These cases are not merged with positive scalar affinity.
16. r_k is a block affinity and L is its negative logarithmic sum. a_k and b_k are common-support masses with different orientations: product b_k is the mass of the part of nu absolutely continuous with respect to mu, and product a_k is the reverse mass. The new corollary exposes these masses in a substantive result statement.
17. D_n(M) includes both finite-marginal density-ratio tails and hence detects finite marginal singular parts as well as lack of uniform integrability. A bounded affinity energy in the general-measure proposition means positive overlap, whereas vanishing uniform two-sided ratio tails means equivalence. The two criteria are not treated as synonyms.
18. Section07's generic block-product and arbitrary-marginal statements explicitly rebind mu, nu and their marginal densities. mu_n continues to mean the first n marginal of the current mu; it equals rho^(tensor n) in the i.i.d. setting. The local p_k,q_k or p_n,q_n densities do not redefine the Fourier functions p,q used in the earlier construction.

First-use and naming review
- Coordinate law, products, Hilbert space, operator spaces, coordinate basis, allowed permutation group, measurable realization, affinity, distance, the two projections, and projected energy are bound in the introduction before their theorem uses.
- Score, scale function, score moments, matrix score, Fisher operator, square-root-density representation, Fourier functions, and finite-dimensional stabilizer distance are introduced before their dependent statements.
- The symbol family P_n is distinct from mathcal P_n. The latter is the finite allowed signed-permutation group; d_n uses that group and appears inside the global theorem. The globalization block projection is now Pi_k, so it does not reuse R. The countable realization group is Gamma, leaving mathcal G_rho for section07's actual equivalence group.
- Adjoint/transpose spelling is canonical A*. Fixed-law f suffixes and redundant dimension superscripts were removed where scope already supplies the data.
- Numbered section filenames and internal section titles/labels are handled by the root structural audit. The first six files preserve logical order: introduction, Fourier characterization, finite-dimensional coercivity, measurable realization/dichotomy, equivalence proof, and scope. Section07 extends this organization with density zeros and the linear equivalence group; the table includes its selected exported object families.

Removed low-burden or competing notation
The table records zero-occurrence checks for R_mu, Gamma_mu, the scalar frequency-energy name, Fourier curvature, the shortened weighted-jet alias, G_(xi,eta), the second Fisher glyph and its redundant law/dimension suffixes, lambda_f, the named local remainder, D_Y/R_X/R_Y aliases, Sigma_f, the law suffix on the permutation group, and d_(n,f). These removals preserve the underlying formulas as explicit expressions or descriptions. This audit records the previous names as change evidence; they are not manuscript aliases.

Explicit scoped exceptions and remaining checks
- L_a versus widehat L_a distinguishes an L2 equivalence class from a Borel representative inside the realization proof; replacing one by the other globally would erase that distinction.
- D_a, Q_M, and F(M,B;...) abbreviate local contraction sums inside one proof. They are retained as proof binders, not named mathematical objects in the paper's interface.
- p,q,r have their Fourier meaning in the construction and its immediate orthogonal reuse. Later q or r bound in other proofs are separate local scalar parameters and are not folded into that family count.
- C_0, C_1, C_lambda, a countable group, and its common carrier are scoped constants/parameters. In particular, C_0 is rebound in globalization; it is not a universally fixed constant across the paper.
- The lexical h count can include the local test-function h in the Fourier proof; its occurrences must be interpreted by scope. The globalization projection was renamed from R_k to Pi_k, and the scalar cutoff from R to L, to keep R associated with the rotational Fourier defect. Section07's block sum L has its own theorem scope; its count excludes the original-six cutoff.
- Terms used as direct descriptions of a formula (location score, scale score, half-density pairing, weighted Fourier jet) are not claimed to pass the separate exported-term test. They introduce no unused symbol or extra proposition parameter.
- The literal phrase projected Hellinger energy is not printed in a result statement, although its defined symbol E_n is central to the main theorem; its decision is resolved by that definition expansion. The exact phrases local Hellinger coercivity and global Hellinger coercivity have fewer than three uses; local and global are resolved as descriptive qualifiers of the same coercivity estimate family. Raw lexical flags remain disclosed below rather than being concealed by padding repetitions.
- Scholar collision-search outcomes belong to the separate search log. This source audit neither performs nor claims a successful Scholar lookup.

Raw lexical flags (editorial decisions resolved in the TSV)
'''+flags+'''

Structural/static integration checks
The final source snapshot contains seven included numbered sections, 157 unique labels, 156 internal reference targets, and 14 cited bibliography keys. A read-only reference scan found no unresolved internal target. Twelve unused bibliography entries were removed. The retained cited entries include the Shepp translation paper introduced with Section07; the bibliography was inspected as source. The build-output ignore path is now /build/ in .gitignore. These are source checks, not compilation or rendering results.

Reproducibility
The counter script used for this snapshot is scripts/audit_notation.py. It regenerates only audit/notation-review.tsv and audit/source-review.txt from the seven section sources. Manual additions to source-review.txt should be appended after the final regeneration. The TSV exposes each regex and count scope; a source hash change requires regeneration before presenting the counts as current.
'''+ '\nSnapshot time (UTC)\n'+datetime.now(timezone.utc).isoformat()+'\n\nSHA-256 source fingerprints\n'+hashes+'\n'
(out/'source-review.txt').write_text(text)
print('Wrote',len(ROWS),'inventory rows.')
print(flags)
print('Result-referenced equation spans:',len(REFERENCED))

"""
Twyn360 Live PGx Agent — powered by Groq (FREE)
=================================================
Uses Groq's free API (llama3 model) with tool calling.
Queries live public databases for ANY gene, variant, or drug.

FREE Setup (2 minutes):
  1. Go to console.groq.com → sign up (no credit card)
  2. API Keys → Create API Key → copy it (starts with gsk_...)
  3. pip install groq requests

Windows CMD:
  set GROQ_API_KEY=gsk_your_key_here
  python agent_groq.py "What is BRCA1?"
  python agent_groq.py "Tell me about warfarin"
  python agent_groq.py "What does VKORC1 do?"
  python agent_groq.py "Explain rs4244285"
"""

import os, sys, json, requests
from groq import Groq

TIMEOUT = 10

# ─────────────────────────────────────────────────────────────────────────────
# LIVE API TOOLS — fetch from real public databases
# ─────────────────────────────────────────────────────────────────────────────

def fetch_gene(gene_symbol: str) -> dict:
    """MyGene.info — any human gene."""
    try:
        r = requests.get(
            "https://mygene.info/v3/query",
            params={
                "q":       gene_symbol,
                "species": "human",
                "fields":  "symbol,name,summary,type_of_gene,pathway.kegg,MIM",
                "size":    1,
            },
            timeout=TIMEOUT,
        )
        r.raise_for_status()
        hits = r.json().get("hits", [])
        if not hits:
            return {"error": f"Gene '{gene_symbol}' not found in MyGene.info"}
        h = hits[0]
        result = {
            "symbol":  h.get("symbol", gene_symbol.upper()),
            "name":    h.get("name", "N/A"),
            "summary": h.get("summary", "No summary available."),
            "type":    h.get("type_of_gene", "N/A"),
            "source":  "MyGene.info",
        }
        pathways = h.get("pathway", {}).get("kegg", [])
        if isinstance(pathways, dict): pathways = [pathways]
        if pathways:
            result["pathways"] = [p.get("name","") for p in pathways[:4]]
        if h.get("MIM"):
            result["omim_id"] = h["MIM"]
        return result
    except requests.exceptions.ConnectionError:
        return {"error": "Cannot reach MyGene.info — check internet connection"}
    except Exception as e:
        return {"error": str(e)}


def fetch_variant(rsid: str) -> dict:
    """MyVariant.info — any rsID."""
    try:
        r = requests.get(
            "https://myvariant.info/v1/query",
            params={
                "q":      rsid.lower().strip(),
                "fields": "dbsnp.rsid,dbsnp.gene,clinvar.rcv.clinical_significance,"
                          "clinvar.rcv.conditions,cadd.consequence,cadd.phred",
                "size":   1,
            },
            timeout=TIMEOUT,
        )
        r.raise_for_status()
        hits = r.json().get("hits", [])
        if not hits:
            return {"error": f"Variant '{rsid}' not found in MyVariant.info"}
        h     = hits[0]
        dbsnp = h.get("dbsnp", {})
        gene  = dbsnp.get("gene", {})
        rcv   = h.get("clinvar", {}).get("rcv", {})
        if isinstance(rcv, list):
            sigs  = list({x.get("clinical_significance","") for x in rcv if x.get("clinical_significance")})
            conds = list({x.get("conditions",{}).get("name","") for x in rcv
                          if isinstance(x.get("conditions"),dict) and x["conditions"].get("name")})[:4]
        elif isinstance(rcv, dict):
            sigs  = [rcv.get("clinical_significance","")]
            c     = rcv.get("conditions",{})
            conds = [c.get("name","")] if isinstance(c,dict) else []
        else:
            sigs, conds = [], []
        return {
            "rsid":                  dbsnp.get("rsid", rsid),
            "gene":                  gene.get("symbol","unknown") if isinstance(gene,dict) else str(gene),
            "clinical_significance": [s for s in sigs if s],
            "conditions":            [c for c in conds if c],
            "consequence":           h.get("cadd",{}).get("consequence","N/A"),
            "cadd_phred":            h.get("cadd",{}).get("phred","N/A"),
            "source":                "MyVariant.info + ClinVar",
        }
    except requests.exceptions.ConnectionError:
        return {"error": "Cannot reach MyVariant.info — check internet connection"}
    except Exception as e:
        return {"error": str(e)}


def fetch_drug(drug_name: str) -> dict:
    """PubChem + OpenFDA — any drug."""
    result = {"drug": drug_name}
    try:
        r = requests.get(
            f"https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/name/"
            f"{requests.utils.quote(drug_name)}/property/"
            "IUPACName,MolecularFormula,MolecularWeight/JSON",
            timeout=TIMEOUT,
        )
        if r.status_code == 200:
            props = r.json()["PropertyTable"]["Properties"][0]
            result["formula"]          = props.get("MolecularFormula","N/A")
            result["molecular_weight"] = props.get("MolecularWeight","N/A")
    except: pass
    try:
        r = requests.get(
            "https://api.fda.gov/drug/label.json",
            params={"search": f"openfda.generic_name:{drug_name}", "limit": 1},
            timeout=TIMEOUT,
        )
        if r.status_code == 200:
            res = r.json().get("results", [])
            if res:
                label = res[0]
                result["mechanism_of_action"] = label.get("mechanism_of_action",["N/A"])[0][:400]
                result["indications"]         = label.get("indications_and_usage",["N/A"])[0][:400]
                result["warnings"]            = label.get("warnings",["N/A"])[0][:300]
    except: pass
    result["source"] = "PubChem + OpenFDA"
    if len(result) <= 2:
        result["note"] = "Limited data found — try the brand name or check spelling"
    return result


def fetch_gene_drug_interactions(gene_symbol: str) -> dict:
    """PharmGKB via MyGene.info."""
    try:
        r = requests.get(
            "https://mygene.info/v3/query",
            params={"q": gene_symbol, "species": "human",
                    "fields": "symbol,name,pharmgkb", "size": 1},
            timeout=TIMEOUT,
        )
        r.raise_for_status()
        hits = r.json().get("hits", [])
        if not hits:
            return {"error": f"Gene '{gene_symbol}' not found"}
        h    = hits[0]
        pgkb = h.get("pharmgkb", {})
        drugs = pgkb.get("drug_labels", []) if isinstance(pgkb, dict) else []
        if isinstance(drugs, dict): drugs = [drugs]
        drug_names = [d.get("name","") for d in drugs if isinstance(d,dict)][:10]
        return {
            "gene":          h.get("symbol", gene_symbol.upper()),
            "gene_name":     h.get("name","N/A"),
            "related_drugs": drug_names if drug_names else ["No PharmGKB drug labels indexed for this gene"],
            "source":        "PharmGKB via MyGene.info",
        }
    except requests.exceptions.ConnectionError:
        return {"error": "Cannot reach MyGene.info — check internet connection"}
    except Exception as e:
        return {"error": str(e)}


# ─────────────────────────────────────────────────────────────────────────────
# TOOL DEFINITIONS (Groq/OpenAI format — same concept, different key names)
# ─────────────────────────────────────────────────────────────────────────────

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "lookup_gene",
            "description": (
                "Look up ANY human gene by HGNC symbol. "
                "Fetches live data from MyGene.info — function, summary, pathways, OMIM. "
                "Works for any gene: BRCA1, TP53, CYP2C19, VKORC1, EGFR, etc."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "gene_symbol": {"type": "string", "description": "HGNC gene symbol e.g. CYP2C19"}
                },
                "required": ["gene_symbol"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "lookup_variant",
            "description": (
                "Look up ANY genetic variant by rsID. "
                "Fetches from MyVariant.info + ClinVar — clinical significance, "
                "associated conditions, functional consequence. "
                "Works for any rsID."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "rsid": {"type": "string", "description": "dbSNP rsID e.g. rs4244285"}
                },
                "required": ["rsid"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "lookup_drug",
            "description": (
                "Look up ANY drug by generic name. "
                "Fetches from PubChem + OpenFDA — mechanism of action, "
                "indications, molecular formula, clinical warnings. "
                "Works for any drug: warfarin, metformin, tamoxifen, etc."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "drug_name": {"type": "string", "description": "Generic drug name e.g. warfarin"}
                },
                "required": ["drug_name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "lookup_gene_drug_interactions",
            "description": (
                "List drugs pharmacogenomically linked to a gene via PharmGKB. "
                "Use when asked 'what drugs does gene X affect?'"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "gene_symbol": {"type": "string", "description": "HGNC gene symbol"}
                },
                "required": ["gene_symbol"],
            },
        },
    },
]


# ─────────────────────────────────────────────────────────────────────────────
# TOOL DISPATCHER
# ─────────────────────────────────────────────────────────────────────────────

def run_tool(name: str, args: dict) -> str:
    print(f"\n  🔧  [{name}] → {args}")
    if name == "lookup_gene":
        result = fetch_gene(args["gene_symbol"])
    elif name == "lookup_variant":
        result = fetch_variant(args["rsid"])
    elif name == "lookup_drug":
        result = fetch_drug(args["drug_name"])
    elif name == "lookup_gene_drug_interactions":
        result = fetch_gene_drug_interactions(args["gene_symbol"])
    else:
        result = {"error": f"Unknown tool: {name}"}
    print(f"  ✅  Got {len(result)} fields from live database")
    return json.dumps(result)


# ─────────────────────────────────────────────────────────────────────────────
# AGENT LOOP (Groq / OpenAI-compatible format)
# ─────────────────────────────────────────────────────────────────────────────

SYSTEM = """You are a clinical pharmacogenomics assistant for the Twyn360 platform.
You have tools that query LIVE public databases (MyGene.info, MyVariant.info,
PubChem, OpenFDA, PharmGKB) for ANY gene, variant, or drug.

Rules:
- ALWAYS call the appropriate tool — never answer from memory alone.
- For genes → lookup_gene (+ lookup_gene_drug_interactions if drug context needed).
- For rsIDs → lookup_variant.
- For drugs → lookup_drug.
- You may call multiple tools if the question spans gene + drug.
- Summarise concisely with clinical relevance highlighted.
- Always cite the data source."""


def run_agent(query: str) -> str:
    client   = Groq()
    messages = [
        {"role": "system",  "content": SYSTEM},
        {"role": "user",    "content": query},
    ]

    while True:
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages    = messages,
            tools       = TOOLS,
            tool_choice = "auto",
            max_tokens  = 1024,
        )

        msg = response.choices[0].message

        # Claude/Groq wants to call tools
        if msg.tool_calls:
            messages.append(msg)                          # add assistant turn
            for tc in msg.tool_calls:
                args       = json.loads(tc.function.arguments)
                result_str = run_tool(tc.function.name, args)
                messages.append({
                    "role":         "tool",
                    "tool_call_id": tc.id,
                    "content":      result_str,
                })
            # loop continues — model will reason over tool results

        # Final answer
        else:
            return msg.content or "No response generated."


# ─────────────────────────────────────────────────────────────────────────────
# ENTRY POINT
# ─────────────────────────────────────────────────────────────────────────────

DEMO_QUERIES = [
    "What does BRCA1 do?",
    "Tell me about variant rs1045642",
    "What is warfarin and how does it work?",
    "What drugs does VKORC1 affect?",
    "Explain the clinical significance of rs4244285",
]


def main():
    if not os.environ.get("GROQ_API_KEY"):
        print("\n" + "═"*65)
        print("  ❌  GROQ_API_KEY not set")
        print("─"*65)
        print("  Get your FREE key in 2 minutes:")
        print("  1. Go to  console.groq.com")
        print("  2. Sign up (no credit card needed)")
        print("  3. API Keys → Create Key → copy it")
        print("─"*65)
        print("  Then in CMD:")
        print("  set GROQ_API_KEY=gsk_your_key_here")
        print("  python agent_groq.py")
        print("═"*65 + "\n")
        sys.exit(1)

    if len(sys.argv) > 1:
        query = " ".join(sys.argv[1:])
        print(f"\n🔍  {query}")
        print("─" * 65)
        print(f"\n🤖  {run_agent(query)}\n")
        return

    print("\n" + "═"*65)
    print("  Twyn360 Live PGx Agent  (Groq — FREE)")
    print("  MyGene.info · MyVariant.info · PubChem · OpenFDA · PharmGKB")
    print("─"*65)
    print("  Ask about ANY gene, variant, or drug")
    print("  Examples:")
    for q in DEMO_QUERIES:
        print(f"    {q}")
    print("  Type 'demo' to run all  |  'quit' to exit")
    print("═"*65)

    while True:
        try:
            query = input("\n> ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\nBye!"); break
        if not query: continue
        if query.lower() in ("quit","exit","q"):
            print("Bye!"); break
        if query.lower() == "demo":
            for q in DEMO_QUERIES:
                print(f"\n🔍  {q}\n" + "─"*65)
                print(f"\n🤖  {run_agent(q)}\n")
            continue
        print("─"*65)
        print(f"\n🤖  {run_agent(query)}")


if __name__ == "__main__":
    main()

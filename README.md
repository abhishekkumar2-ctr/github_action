# DP_LOGIC — DAG Validation via GitHub Actions (Airflow 2.6.2)

Ye project dikhata hai ki kaise GitHub Actions se Airflow DAGs ko automatically
validate kiya jaata hai (syntax + import + DAG-integrity errors), aur agar sab
sahi hai to PR auto-merge ho jaata hai.

```
DP_LOGIC/
├── airflow_home/
│   └── dags/
│       ├── dag_1.py                    # simple valid DAG
│       ├── dag_2.py                    # uses pandas
│       ├── dag_3.py                    # uses requests, chained tasks
│       └── dag_broken_example.py.txt   # rename to .py to test a FAILING check
├── scripts/
│   └── validate_dags.py                # the actual validation logic
├── .github/workflows/
│   └── dag-validation.yml              # the GitHub Action
├── requirements.txt                    # external libraries your DAGs need
├── .gitignore
└── README.md
```

---

## PART A — Local par test karo (push karne se pehle)

### 1. Python venv banao

```bash
cd DP_LOGIC
python3 -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
```

### 2. Airflow 2.6.2 install karo (constraints ke sath — zaroori hai)

```bash
export AIRFLOW_VERSION=2.6.2
export PYTHON_VERSION=3.9        # apne python version se match karo
export CONSTRAINT_URL="https://raw.githubusercontent.com/apache/airflow/constraints-${AIRFLOW_VERSION}/constraints-${PYTHON_VERSION}.txt"

pip install "apache-airflow==${AIRFLOW_VERSION}" --constraint "${CONSTRAINT_URL}"
pip install -r requirements.txt --constraint "${CONSTRAINT_URL}"
```

### 3. Isolated AIRFLOW_HOME set karo (apni real dev DB se alag rakhne ke liye)

```bash
export AIRFLOW_HOME=$(pwd)/airflow_home_ci
airflow db init
```

### 4. Validation script chalao

```bash
python scripts/validate_dags.py
```

Agar sab DAGs sahi hain to ye output milega:
```
✅ Successfully validated 3 DAG(s):
   - dag_1_hello_world
   - dag_2_pandas_demo
   - dag_3_etl_demo
```

### 5. (Optional) Failure case test karo

```bash
mv airflow_home/dags/dag_broken_example.py.txt airflow_home/dags/dag_broken_example.py
python scripts/validate_dags.py
```
Ye ❌ error dikhayega aur exit code 1 dega — matlab CI me bhi ye PR ko fail
kar dega. Test hone ke baad wapas rename kar do (ya delete kar do):
```bash
mv airflow_home/dags/dag_broken_example.py airflow_home/dags/dag_broken_example.py.txt
```

---

## PART B — GitHub par push karo

### 1. Naya repo banao (agar already nahi hai)

```bash
cd DP_LOGIC
git init
git add .
git commit -m "Initial commit: DAGs + GitHub Actions DAG validation"
git branch -M main
git remote add origin https://github.com/<your-username>/<your-repo>.git
git push -u origin main
```

### 2. Repo settings configure karo

**a) Read/write permissions on**
`Settings → Actions → General → Workflow permissions` → select
**"Read and write permissions"** → Save
*(Ye zaroori hai warna auto-merge step fail hoga)*

**b) Auto-merge feature on**
`Settings → General` → scroll down → check **"Allow auto-merge"**

**c) Branch protection lagao**
`Settings → Branches → Add branch protection rule`
- Branch name pattern: `main`
- ✅ "Require status checks to pass before merging"
- Us list me se `validate-dags` select karo (pehli baar workflow run hone
  ke baad hi ye dropdown me dikhega — agar abhi nahi dikhta to ek dummy PR
  bana ke pehla run trigger kar do, phir wapas aa kar select karo)
- ✅ "Require a pull request before merging" (recommended)
- Save changes

---

## PART C — Test karo (end-to-end)

### 1. Ek naya branch banao aur DAG me chota change karo

```bash
git checkout -b test-dag-validation
echo "# small comment change" >> airflow_home/dags/dag_1.py
git add .
git commit -m "test: trigger dag validation"
git push origin test-dag-validation
```

### 2. GitHub par PR banao

`main` ← `test-dag-validation` — PR create karo.

### 3. Dekho kya hota hai

- GitHub Actions tab me `DAG Validation` workflow automatically start hoga
- `validate-dags` job sabhi DAGs load karega
- Agar sab sahi hai → job green ✅ ho jaayega → `enable-auto-merge` job
  chalega → PR **automatically merge** ho jaayega required checks pass
  hone ke baad

### 4. Failure test (optional, recommended once)

Same PR me `dag_broken_example.py.txt` ko `.py` me rename karke push karo.
Is baar workflow ❌ fail hoga, aur PR **merge nahi hoga** — jo ki expected
aur correct behavior hai.

---

## Aage kya customize karna hai

| Kya karna hai | Kahan change karo |
|---|---|
| Apni real libraries add karo | `requirements.txt` |
| DAG folder path alag hai | `scripts/validate_dags.py` me `DAG_FOLDER` |
| Python version alag hai | `.github/workflows/dag-validation.yml` me `PYTHON_VERSION` |
| Sirf validate karo, auto-merge nahi chahiye | `enable-auto-merge` job pura hata do workflow file se |
| Human review bhi mandatory chahiye | Branch protection me "Require approvals" bhi ✅ karo — tab auto-merge tabhi hoga jab approval + checks dono pass hon |

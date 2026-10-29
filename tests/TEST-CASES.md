# Test Cases: Demo Names and Login Role

Run the automated checks with:

```powershell
python -m unittest discover -s tests -v
```

| ID | Test | Input / action | Expected result | Actual result | Status |
|---|---|---|---|---|---|
| TC-LOGIN-01 | Default login role | Open `/` | Student role is selected; Student, Admin, and Teacher options are visible | Student is selected; all three options are rendered | PASS |
| TC-LOGIN-02 | Student login | Select Student; `student` / `Student@123` | Login succeeds as Student | Login succeeds; session role is `student` | PASS |
| TC-LOGIN-03 | Admin login | Select Admin; `admin` / `Admin@123` | Login succeeds as Admin | Login succeeds; session role is `admin` | PASS |
| TC-LOGIN-04 | Teacher login | Select Teacher; `teacher` / `Teacher@123` | Login succeeds as Teacher | Login succeeds; session role is `teacher` | PASS |
| TC-LOGIN-05 | Role does not match account | Select Student; `admin` / `Admin@123` | Login is rejected without creating a session | HTTP 401; credentials rejected | PASS |
| TC-LOGIN-06 | Missing or invalid role | Submit without a role or with `superuser` | Request is rejected with a validation error | HTTP 400 for both inputs | PASS |
| TC-DATA-01 | Fresh demo seed names | Initialize an empty database | Forty unique Indian names are present instead of generic numbered names | Seed contains all 40 configured names, unique | PASS |
| TC-DATA-02 | Existing default demo names | Restart with `Student 01` and its original demo email | Default demo row is renamed; customized names remain unchanged | Generic row is updated to Aarav Sharma and matching demo email | PASS |

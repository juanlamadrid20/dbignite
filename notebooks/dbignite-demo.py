# Databricks notebook source
# MAGIC %md 
# MAGIC # Analysis of FHIR Bundles using SQL and Python
# MAGIC 
# MAGIC <img src="http://hl7.org/fhir/assets/images/fhir-logo-www.png" width = 10%>
# MAGIC 
# MAGIC In this demo: 
# MAGIC   1. We use datarbicks `dbignite` package to ingest FHIR bundles (in `json` format) into deltalake
# MAGIC   2. Create a patient-level dashboard from the bundles
# MAGIC   3. Create cohorts
# MAGIC   4. Investigate rate of hospital admissions among covid patients and explore the effect of SDOH and disease history in hospital admissions
# MAGIC   5. Create a feature store of patient features, and use the feature store to create a training dataset for downstream ML workloads, using [databricks feture store](https://docs.databricks.com/applications/machine-learning/feature-store/index.html#databricks-feature-store). 
# MAGIC <br>
# MAGIC </br>
# MAGIC <img src="https://hls-eng-data-public.s3.amazonaws.com/img/FHIR-RA.png" width = 70%>
# MAGIC 
# MAGIC ### Data
# MAGIC The data used in this demo is generated using [synthea](https://synthetichealth.github.io/synthea/). We used [covid infections module](https://github.com/synthetichealth/synthea/blob/master/src/main/resources/modules/covid19/infection.json), which incorporates patient risk factors such as diabetes, hypertension and SDOH in determining outcomes. The data is available at `s3://hls-eng-data-public/data/synthea/fhir/fhir/`. 

# COMMAND ----------

# MAGIC %md
# MAGIC ## 0. Configuration

# COMMAND ----------

# MAGIC %md
# MAGIC ```
# MAGIC pip install git+https://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@github.com/databrickslabs/dbignite.git@amir
# MAGIC ```

# COMMAND ----------

# MAGIC %md
# MAGIC Now we can import the module and start using it.

# COMMAND ----------

from dbignite.data_model import Transformer

# COMMAND ----------

# MAGIC %md We have stored simulated FHIR bundles in `s3://hls-eng-data-public/data/synthea/fhir/fhir/` and will directly access those from the notebook.

# COMMAND ----------

BUNDLE_PATH="s3://hls-eng-data-public/data/synthea/fhir/fhir/"

# COMMAND ----------

# MAGIC %md
# MAGIC Before we start, let's take a look at the files:

# COMMAND ----------

# DBTITLE 1,list FHIR bundles
files=dbutils.fs.ls(BUNDLE_PATH)
data_size=sum([m.size for m in files])//1e9
n_bundles=len(files)
displayHTML(f'There are <b>{n_bundles}</b> with a a total size of <b>{data_size}</b> Gb')
display(files,10)

# COMMAND ----------

# MAGIC %md
# MAGIC ## 1. Load FHIR bundles

# COMMAND ----------

# MAGIC %md
# MAGIC Let's take a look at one of the files

# COMMAND ----------

sample_bundle=dbutils.fs.ls(BUNDLE_PATH)[0].path
print(dbutils.fs.head(sample_bundle,500))

# COMMAND ----------

# MAGIC %md
# MAGIC ## 2. Extract resources from the bundles
# MAGIC The`fhir_bundles_to_omop_cdm` method extracts resources from the FHIR bunldes and creates: `person`, `condition`, `procedure_occurrence` and `encounters` in the `cdm_database`

# COMMAND ----------

# DBTITLE 1,patient dashboard 
cdm_database='dbignite_demo' 
transformer=Transformer(spark)
cdm=transformer.fhir_bundles_to_omop_cdm(BUNDLE_PATH, cdm_database=cdm_database)

# COMMAND ----------

# DBTITLE 1,list all tables
sql(f'use {cdm.listDatabases()[0]}')
display(sql('show tables'))

# COMMAND ----------

# MAGIC %md
# MAGIC In addition to tables formed based on clinical records, we also can add two tables, `cohort` and `cohort_definition` tables to host cohorts. See [The Book Of OHDSI](https://ohdsi.github.io/TheBookOfOhdsi/CommonDataModel.html#cdm-standardized-tables). As an example, we later add covid and admission cohorts to this shcema (see section 4)

# COMMAND ----------

# MAGIC %sql
# MAGIC CREATE
# MAGIC OR REPLACE TABLE cohort (
# MAGIC   cohort_definition_id LONG,
# MAGIC   person_id STRING,
# MAGIC   cohort_start_date DATE,
# MAGIC   cohort_end_date DATE
# MAGIC ) USING DELTA;
# MAGIC 
# MAGIC CREATE
# MAGIC OR REPLACE TABLE cohort_definition (
# MAGIC   cohort_definition_id LONG,
# MAGIC   cohort_definition_name STRING,
# MAGIC   cohort_definition_description STRING,
# MAGIC   cohort_definition_syntax STRING,
# MAGIC   cohort_initiation_date DATE
# MAGIC ) USING DELTA;

# COMMAND ----------

# MAGIC %md
# MAGIC ## 3.Data Analysis
# MAGIC Now let's take a quick look at the data.

# COMMAND ----------

# MAGIC %md
# MAGIC ### Person Table

# COMMAND ----------

# MAGIC %sql
# MAGIC select * from person
# MAGIC limit 10

# COMMAND ----------

# MAGIC %md
# MAGIC ### Condition Table

# COMMAND ----------

# MAGIC %sql
# MAGIC select * from condition
# MAGIC limit 10

# COMMAND ----------

# DBTITLE 1,Top 20 common conditions
# MAGIC %sql
# MAGIC select condition_code, condition_status, count(*) as counts
# MAGIC from condition
# MAGIC group by 1,2
# MAGIC order by 3 desc
# MAGIC limit 20

# COMMAND ----------

# DBTITLE 1,age distribution among covid-19 patients
# MAGIC %sql
# MAGIC select 10*floor((year(CURRENT_DATE) - year_of_birth)/10) as age_group, count(*) as count from person p
# MAGIC join condition c on p.person_id=c.person_id
# MAGIC where c.condition_code=840539006
# MAGIC group by 1
# MAGIC order by 1

# COMMAND ----------

# MAGIC %md
# MAGIC ### procedure_occurrence Table

# COMMAND ----------

# MAGIC %sql 
# MAGIC select * from procedure_occurrence
# MAGIC limit 10

# COMMAND ----------

# DBTITLE 1,to 10 most common procedures
# MAGIC %sql
# MAGIC select procedure_code,procedure_code_display, count(*) as count from procedure_occurrence
# MAGIC group by 1,2
# MAGIC order by 3 desc
# MAGIC limit 10

# COMMAND ----------

# MAGIC %md
# MAGIC ### Encounter Table

# COMMAND ----------

# DBTITLE 1,Encounters
# MAGIC %sql
# MAGIC select * from encounter
# MAGIC limit 10

# COMMAND ----------

# DBTITLE 1,top 10 encounters
# MAGIC %sql
# MAGIC select encounter_status, count(*) as count
# MAGIC from encounter
# MAGIC group by 1
# MAGIC order by 2 desc
# MAGIC limit 10

# COMMAND ----------

# MAGIC %md
# MAGIC ### Person Dashboard
# MAGIC In addition to creating a database of clinical entities extratced from FHIR bundles, using `dbinterop` you can create a patient-centric dashboard, that creates a unified 
# MAGIC view of a patient.

# COMMAND ----------

person_dashboard=transformer.omop_cdm_to_person_dashboard(cdm).summary()
display(person_dashboard)

# COMMAND ----------

from pyspark.sql.functions import *
person_dashboard.filter("person_id='6efa4cd6-923d-2b91-272a-0f5c78a637b8'").select(explode('conditions')).display()


# COMMAND ----------

# MAGIC %md
# MAGIC ## 4. Covid Outcomes Analysis
# MAGIC 
# MAGIC Now, let's take a deeper look at the data and explore factors that might affect covid outcomes. To ensure better reproducibility and organizing the data, we first create patient cohorts based on the criteria of interest (being admitted to hospital, infection status, disease hirtory etc). We then proceed to create features based on cohorts and add the results to databricks feature store.
# MAGIC To make data access easier we added cohort tables to the `cdm_dbinterop` database (similar to OMOP's results schema)

# COMMAND ----------

# MAGIC %md
# MAGIC ### Create cohorts
# MAGIC Let's define a function that adds a cohort to the database, given a set of parameters including the inclusion criteria which is specified as a sql clause.

# COMMAND ----------

import uuid
def create_cohort(cohort_definition_name,cohort_definition_description, target_table, start_col,end_col,sql_where_clause):
  uid=uuid.uuid4().fields[0]
  sql_str=f"""select {uid} as cohort_definition_id,
                              person_id,
                              to_date({start_col}) as cohort_start_date,
                              to_date({end_col}) as cohort_end_date
                              from {target_table} where {sql_where_clause}"""
  
  sql(f"INSERT INTO {cdm_database}.cohort {sql_str}")
  sql(f"""
      INSERT INTO {cdm_database}.cohort_definition
        select {uid} as cohort_definition_id,
        '{cohort_definition_name}' as cohort_definition_name,
        '{cohort_definition_description}' as cohort_definition_description,
        '{sql_str}' as cohort_definition_syntax,
        current_date() as cohort_initiation_date
        """)

# COMMAND ----------

# DBTITLE 1,add cohorts
#specify encounter codes for all hospital admissions
hospital_encounters={
  'hospital-admission-for-isolation': 1505002,
  'hospital-admission':32485007,
  'admission-to-icu':305351004,
  'hospital-admission-for-observation':76464004
}
### all patients with confirmed covid case
create_cohort('covid','patinets with covid','condition','condition_start_datetime','condition_end_datetime','condition_code in (840539006)')
### all patintes who have been admitted to hospital (including ICU visits)
create_cohort('admission','patients admitted','encounter','encounter_period_start','encounter_period_end','encounter_code in (1505002, 32485007, 305351004, 76464004)')

# COMMAND ----------

# DBTITLE 1,admission cohort
# MAGIC %sql
# MAGIC select c.cohort_definition_id,person_id,cohort_start_date,cohort_end_date from cohort c
# MAGIC join cohort_definition cd
# MAGIC where cd.cohort_definition_id = c.cohort_definition_id
# MAGIC and cd.cohort_definition_name = 'admission'

# COMMAND ----------

# DBTITLE 1,cohort definitions
# MAGIC %sql
# MAGIC select *
# MAGIC from cohort_definition
# MAGIC limit 10

# COMMAND ----------

# DBTITLE 1,Percentage of covid patients admitted to the hospital
from pyspark.sql.functions import *

covid_cohort_df=sql("select c.person_id, cohort_start_date as covid_start from cohort c join cohort_definition cd where cd.cohort_definition_name='covid' and cd.cohort_definition_id=c.cohort_definition_id")

admission_cohort_df=sql("select person_id, cohort_start_date as admission_start from cohort c join cohort_definition cd where cd.cohort_definition_name='admission' and cd.cohort_definition_id=c.cohort_definition_id")

covid_admissions_df=(
  covid_cohort_df
  .join(admission_cohort_df,how='left',on='person_id')
  .withColumn('is_admitted',
              when(col('admission_start').between(col('covid_start'),date_add(col('covid_start'),30)),1).otherwise(0)
             )
)
covid_admissions_df.selectExpr('100*avg(is_admitted) as percent_admitted').display()

# COMMAND ----------

# MAGIC %md
# MAGIC Now let us add disease history and SDOH information

# COMMAND ----------

# DBTITLE 1,patient comorbidity history
from pyspark.sql.functions import *

conditions_list = {
  "full-time-employment": 160903007,
  "part-time-employment": 160904001,
  "not-in-labor-force": 741062008,
  "received-higher-education": 224299000,
  "has-a-criminal-record": 266948004,
  "unemployed": 73438004,
  "refugee": 446654005,
  "misuses-drugs":361055000,
  "obesity":162864005,
  "prediabetes":15777000,
  "hypertension":59621000,
  "diabetes":44054006,
  "coronary-heart-disease":53741008
}

def add_history(df,cond_name,cond_code):
  out_df = (
    df
    .withColumn(f'history_of_{cond_name}', when(exists('conditions', lambda c: c['condition_code'].contains(cond_code)),1).otherwise(0))
  )
  return(out_df)

def create_patient_history_table(conditions_list):
  patient_history_df = person_dashboard.selectExpr('person_id', 'conditions')
  for cond_name,cond_code in conditions_list.items():
    patient_history_df = add_history(patient_history_df,cond_name,cond_code)
    
  patient_history_df = patient_history_df.drop('conditions')
  return(patient_history_df)

# COMMAND ----------

# MAGIC %md
# MAGIC Note: here, we directly create a dataset of disease and SDOH historeis, represented as binary values. Alternatively, for each condition and a given timeframe, you can add a cohort of patients, having had that condition and add to the cohort table.

# COMMAND ----------

patient_history_df = create_patient_history_table(conditions_list)
display(patient_history_df,10)

# COMMAND ----------

patient_history_df.count()

# COMMAND ----------

# MAGIC %md
# MAGIC ### Analyze correlation between different factors impacting outcomes
# MAGIC Now let's take a deeper look into the correlations between different factors. To conduct a complete analysis we look at the [mutual information](https://en.wikipedia.org/wiki/Mutual_information) between different features in our dataset. To calculate mutual information we use [`normalized_mutual_info_score`](https://scikit-learn.org/stable/modules/generated/sklearn.metrics.normalized_mutual_info_score.html) from `sklearn`.

# COMMAND ----------

patient_covid_data_df=covid_admissions_df.select('person_id','is_admitted')

patient_covid_hist_df=(
  patient_history_df
  .join(covid_admissions_df.select('person_id','is_admitted'), on='person_id')
)
patient_covid_hist_df.display(10)

# COMMAND ----------

import numpy as np
import pandas as pd
from sklearn.metrics.cluster import normalized_mutual_info_score
def mutual_info(pdf,col1,col2):
  X = pdf[col1]
  Y = pdf[col2]
  IXY=normalized_mutual_info_score(X, Y)
  return(IXY)

# COMMAND ----------

# DBTITLE 1,Mutual information between different features
patient_covid_hist_pdf=patient_covid_hist_df.toPandas()
cols=patient_covid_hist_pdf.drop('person_id',axis=1).columns
ll=[]
for col1 in cols:
  for col2 in cols:
    ll+=[mutual_info(patient_covid_hist_pdf,col1,col2)]
cols = [m.replace('history_of_','') for m in cols]
mutI_pdf=pd.DataFrame(np.array(ll).reshape(len(cols),len(cols)),index=cols,columns=cols)
plot_pdf=mutI_pdf**(1/3)
plot_pdf.style.background_gradient(cmap='Blues')

# COMMAND ----------

# MAGIC %md
# MAGIC Looking at the table above, we see that the highest correlation is between hospital admissions and hypertension, followed by coronary heart-disease, which seems consistent with the fatcors taken into account in the synthea modlude for covid infections. On the SDOH side, we see high correlations with part-time employment status. However, we also see high correlation with criminal records which can be example of a spouroious correlation due to small sample size (100).

# COMMAND ----------

# MAGIC %md
# MAGIC ## License
# MAGIC Copyright / License info of the notebook. Copyright Databricks, Inc. [2021].  The source in this notebook is provided subject to the [Databricks License](https://databricks.com/db-license-source).  All included or referenced third party libraries are subject to the licenses set forth below.
# MAGIC 
# MAGIC |Library Name|Library License|Library License URL|Library Source URL| 
# MAGIC | :-: | :-:| :-: | :-:|
# MAGIC |Synthea|Apache License 2.0|https://github.com/synthetichealth/synthea/blob/master/LICENSE| https://github.com/synthetichealth/synthea|
# MAGIC |The Book of OHDSI | Creative Commons Zero v1.0 Universal license.|https://ohdsi.github.io/TheBookOfOhdsi/index.html#license|https://ohdsi.github.io/TheBookOfOhdsi/|

# COMMAND ----------

# MAGIC %md
# MAGIC ### Disclaimers
# MAGIC Databricks Inc. (“Databricks”) does not dispense medical, diagnosis, or treatment advice. This Solution Accelerator (“tool”) is for informational purposes only and may not be used as a substitute for professional medical advice, treatment, or diagnosis. This tool may not be used within Databricks to process Protected Health Information (“PHI”) as defined in the Health Insurance Portability and Accountability Act of 1996, unless you have executed with Databricks a contract that allows for processing PHI, an accompanying Business Associate Agreement (BAA), and are running this notebook within a HIPAA Account.  Please note that if you run this notebook within Azure Databricks, your contract with Microsoft applies.

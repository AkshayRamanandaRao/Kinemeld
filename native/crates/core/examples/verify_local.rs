//! Actual Windows host smoke: owned service, validation, MBDyn solve and portable project.
use mbdyn_studio_core::{BackendService, Model, ProjectDocument, ProjectSession, SaveMode};
use serde_json::json;
use std::{path::PathBuf, time::{SystemTime,UNIX_EPOCH}};

fn main() -> Result<(),Box<dyn std::error::Error>> {
    let args:Vec<_>=std::env::args_os().collect();
    let workspace=PathBuf::from(args.get(1).ok_or("workspace argument required")?);
    let python=PathBuf::from(args.get(2).ok_or("python executable argument required")?);
    let mut service=BackendService::start(&workspace,&python)?;
    let client=service.client().clone();
    let health=client.health()?; let status=client.status()?;
    let examples=client.examples()?;
    let mut model:Model=serde_json::from_value(examples.iter().find(|example|example.id=="pendulum").ok_or("pendulum missing")?.model.clone())?;
    model.simulation.duration=0.5;
    let validation=client.validate(&model)?;
    assert!(validation.valid);
    let deck=client.deck(&model)?; assert!(deck.deck.contains("final time: 0.5"));
    let result=client.run(&model)?;
    let csv=String::from_utf8(client.download(result.files.get("csv").ok_or("CSV absent")?)?)?;
    let mut document=ProjectDocument::new(serde_json::to_value(&model)?)?;
    let mut saved_result=serde_json::to_value(&result)?;
    saved_result["rawCsv"]=json!(csv);
    document.result=Some(saved_result);
    let mut project=ProjectSession::new(document.clone())?;
    let stamp=SystemTime::now().duration_since(UNIX_EPOCH)?.as_nanos();
    let path=workspace.join("runs").join(format!("native-project-verification-{stamp}.json"));
    project.save_as(&path,SaveMode::CreateNew)?;
    let reopened=ProjectSession::open(&path)?;
    assert!(reopened.document()==&document,"Template project roundtrip changed data");
    let catalog=client.source_catalog()?;
    let source_result=client.run_source("srscm")?;
    assert!(source_result.samples[0].get("nodes").and_then(|nodes|nodes.as_array()).is_some_and(|nodes|!nodes.is_empty()));
    let source_model=source_result.model.as_ref().ok_or("source model missing")?;
    assert!(client.validate_model(source_model)?.valid);
    let source_deck=client.deck_model(source_model)?;
    assert!(!source_deck.deck.is_empty());
    let source_csv=String::from_utf8(client.download(source_result.files.get("csv").ok_or("source CSV absent")?)?)?;
    let mut source_document=ProjectDocument::new(source_model.clone())?;
    let mut source_saved=serde_json::to_value(&source_result)?;
    source_saved["rawCsv"]=json!(source_csv);
    source_document.result=Some(source_saved);
    let source_path=workspace.join("runs").join(format!("native-source-project-verification-{stamp}.json"));
    ProjectSession::new(source_document.clone())?.save_as(&source_path,SaveMode::CreateNew)?;
    assert!(ProjectSession::open(&source_path)?.document()==&source_document,"Source project roundtrip changed data");
    let backend_log=service.log_path().to_path_buf();
    service.stop()?;
    assert!(!service.is_running()?);
    assert!(client.health().is_err());
    let report=serde_json::to_string_pretty(&json!({"passed":true,"host":std::env::consts::OS,"health":health,"solver":status.solver,"runId":result.run_id,"projectPath":path,"projectBytes":std::fs::metadata(&path)?.len(),"samples":result.samples.len(),"csvLines":csv.lines().count(),"sourceRunId":source_result.run_id,"sourceSamples":source_result.samples.len(),"sourceCatalogCount":catalog["examples"].as_array().map(|items|items.len()),"sourceProjectPath":source_path,"sourceProjectBytes":std::fs::metadata(&source_path)?.len(),"sourceCsvLines":source_csv.lines().count(),"backendLog":backend_log,"ownedBackendStopped":true}))?;
    let evidence=workspace.join("native/crates/core/evidence");std::fs::create_dir_all(&evidence)?;
    std::fs::write(evidence.join("windows-host-verification.json"),&report)?;
    println!("{report}");
    Ok(())
}

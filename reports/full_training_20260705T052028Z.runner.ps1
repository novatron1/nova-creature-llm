Set-Location -LiteralPath 'C:\Users\nova\Documents\NOVA LLM CREATURE DESKTOP'
& py -3 scripts\run_transformer_hyper_training.py --seed 20260622 --route-epochs 80 --role-epochs 30 > 'C:\Users\nova\Documents\NOVA LLM CREATURE DESKTOP\reports\full_training_20260705T052028Z.out.txt' 2> 'C:\Users\nova\Documents\NOVA LLM CREATURE DESKTOP\reports\full_training_20260705T052028Z.err.txt'
Set-Content -LiteralPath 'C:\Users\nova\Documents\NOVA LLM CREATURE DESKTOP\reports\full_training_20260705T052028Z.exit.txt' -Value $LASTEXITCODE

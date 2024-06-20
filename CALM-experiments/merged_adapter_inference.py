import torch
from peft import PeftModel, PeftConfig
from transformers import AutoModelForCausalLM, AutoTokenizer

base_model = "meta-llama/Llama-2-7b-hf"
compute_dtype = getattr(torch, "float16")

model = AutoModelForCausalLM.from_pretrained(
        base_model, device_map={"": 0})

tokenizer = AutoTokenizer.from_pretrained(base_model, use_fast=True)

model = PeftModel.from_pretrained(model, "schaturv/llama2-7b-arithmetic-calculations-adapter", adapter_name="arithmetic")

model.load_adapter("schaturv/llama2-7b-key-value-adapter", adapter_name="pairings")

# print(model)

# combining adapters using cat
model.add_weighted_adapter(["arithmetic", "pairings"], [1.0,1.0], combination_type="cat", adapter_name="pairings_arithmetic")

# remove the single adapters
model.delete_adapter("arithmetic")
model.delete_adapter("pairings")
model.save_pretrained("schaturv/pairings_arithmetic")
model.config.to_json_file("adapter_config.json")
# model.push_to_hub("schaturv/pairings_arithmetic")

model = PeftModel.from_pretrained(model, "adapter_config.json")

# prompt generating function
def generate(prompt):
  tokenized_input = tokenizer(prompt, return_tensors="pt")
  input_ids = tokenized_input["input_ids"].cuda()

  generation_output = model.generate(
          input_ids=input_ids,
          num_beams=1,
          return_dict_in_generate=True,
          output_scores=True,
          max_new_tokens=130

  )
  for seq in generation_output.sequences:
      output = tokenizer.decode(seq, skip_special_tokens=True)
      print(output.strip())





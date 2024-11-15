"""
Code for VQ-SVG-LLAMA-Understanding
"""
import torch  
import torch.nn as nn 
import torch.nn.functional as F
from transformers import LlamaForCausalLM  
from modelzipper.tutils import *


class VQSVGLlamaUnderstanding(LlamaForCausalLM):  
    def __init__(self, config, codebook_size, convert_token_weight=1.5, tokenizer=None, vqvae=None):  
        super(VQSVGLlamaUnderstanding, self).__init__(config)
        self.tokenizer = tokenizer
        self.convert_token_weight = convert_token_weight
        self.vqvae = vqvae
        self.codebook_size = codebook_size
        self.vqvae_embedding = nn.Embedding(self.codebook_size, config.hidden_size)
        self.vqvae_adapter = nn.Linear(config.hidden_size, config.hidden_size)

        self.post_init()
        if config.frozen_llm: 
            print_c("Attention! Part of the parameters are freezed!")
            self.requires_grad_ = False 
            self.input_adapter.requires_grad_ = True
            self.output_adapter.requires_grad_ = True
    
    def init_vqvae(self, vqvae):
        self.vqvae = vqvae
        self.vqvae.model.eval()
        for param in self.vqvae.model.parameters():
            param.requires_grad = False

    def set_tokenizer(self, tokenizer):
        self.tokenizer = tokenizer

    def load_state_dict(self, state_dict: Mapping[str, Any], strict: bool = True):
        return super().load_state_dict(state_dict, strict)
        
    def forward(self, prompt_prefix_ids=None, prompt_prefix_attention_mask=None, prompt_suffix_ids=None, prompt_suffix_attention_mask=None, response_ids=None, response_attention_mask=None, response_labels=None, svg_tensors=None, svg_attention_mask=None, **kwargs): 
        """
            text_input_ids: B x L 
            text_attention_mask: B x L,
            text_labels: B x L,
            svg_tensors: B x L (x l_bins),  depend on offline or online mode
            svg_padding_mask: B x L,
            response_ids: B x L,
            response_attention_mask: B x L,
        """
        # embedding text
        text_embedding_module = self.base_model.get_input_embeddings()
        prefix_embeddings = text_embedding_module(prompt_prefix_ids)
        suffix_embeddings = text_embedding_module(prompt_suffix_ids)
        responese_embeddings = text_embedding_module(response_ids)
        
        svg_token_ids = svg_tensors

        svg_token_embeddings = self.vqvae_embedding(svg_token_ids)
        svg_token_embeddings = self.vqvae_adapter(svg_token_embeddings) 

        input_embeddings = torch.cat([prefix_embeddings, svg_token_embeddings, suffix_embeddings, responese_embeddings], dim=1) # concate the text embedding and svg token embedding
        
        attention_masks = torch.cat([prompt_prefix_attention_mask, svg_attention_mask, prompt_suffix_attention_mask, response_attention_mask], dim=1) # concate the text attention mask and svg padding mask 

        outputs = self.model(
            input_ids=None, 
            attention_mask=attention_masks,
            inputs_embeds=input_embeddings, 
        )
        hidden_states = outputs[0]

        response_width = response_ids.size(1)
        text_logits = self.lm_head(hidden_states[:, -response_width:, :]).float()
        loss = None
        if response_labels is not None:
            # Shift so that tokens < n predict n
            shift_logits = text_logits[..., :-1, :].contiguous()  # last logits is convert_token logits
            shift_labels = response_labels[..., 1:].contiguous() # last token is convert_token
            # Flatten the tokens
            shift_logits = shift_logits.view(-1, self.config.vocab_size)
            shift_labels = shift_labels.view(-1)
            # Enable model parallelism
            shift_labels = shift_labels.to(shift_logits.device)
            loss = F.cross_entropy(shift_logits, shift_labels)

        output = (text_logits,) + outputs[1:]
        return (loss,) + output if loss is not None else output
    
    @torch.no_grad()
    def generate(self, text_input_ids=None, text_attention_mask=None, past_key_values=None, max_generate_length=1024, do_sample=False, top_p=0.9, top_k=40, temperature=0.7) -> List[torch.LongTensor]:
        
        assert self.svg_begin_token_id not in text_input_ids, "You should not add svg_begin_token_id in text_input_ids, since it will automactically add svg_begin_token_id in the beginning of svg_tensors during the inference!"
        
        batch_size = text_input_ids.size(0)
  
        # initial eos_generated_mask to False for all samples as no sample has generated eos_token yet
        eos_generated_mask = torch.zeros(batch_size, dtype=torch.bool)
        
        outputs = self.model(
            input_ids=text_input_ids,
            past_key_values=past_key_values,
            attention_mask=text_attention_mask,
            use_cache=True,
        )
        last_hidden_state = outputs.last_hidden_state
        past_key_values = outputs.past_key_values
        text_width = text_input_ids.size(1)
        
        generated_ids = [text_input_ids[:, i].unsqueeze(1) for i in range(text_width)]
        
        # create svg_begin token id and embeddings
        svg_begin_token_ids = torch.empty(text_input_ids.size(0)).fill_(self.svg_begin_token_id).long().to(last_hidden_state.device)
        
        prev_svg_token_ids = svg_begin_token_ids.unsqueeze(1)
        
        for _ in range(max_generate_length - 1):
            input_embeddings = self.vqvae_embedding(prev_svg_token_ids)
            outputs = self.model(
                input_ids=None,
                past_key_values=past_key_values,
                inputs_embeds=input_embeddings, 
                use_cache=True,
            )
            last_hidden_state = outputs.last_hidden_state
            past_key_values = outputs.past_key_values
            pred_logits = self.vqvae_head(last_hidden_state).float()
            
            if do_sample:
                pred_svg_idx = top_k_top_p_sampling(pred_logits[:, -1, :], top_k=top_k, top_p=top_p, temperature=temperature)
            else:
                pred_svg_idx = pred_logits[:, -1, :].argmax(dim=-1).unsqueeze(1)
            
            # update eos_generated_mask, as some samples generate svg_eos_token
            eos_generated_mask |= (pred_svg_idx.squeeze(1) == self.svg_end_token_id)  

            # add the predicted svg token embedding to input_embeddings according to pred_svg_idx
            current_step_ids = torch.full((batch_size, 1), self.svg_end_token_id, dtype=torch.long, device=last_hidden_state.device)  
            current_step_ids[~eos_generated_mask] = pred_svg_idx[~eos_generated_mask]  
            generated_ids.append(current_step_ids)  
            
            if eos_generated_mask.all():  # all samples have generated eos_token, break
                break
            
            prev_svg_token_ids = current_step_ids
        
        generated_ids = torch.cat(generated_ids, dim=1)  # B x gen_length
        generated_mask = ~(generated_ids == self.svg_end_token_id)  # B x gen_length
        post_processed_ids = []  # List[Tensor]
        
        for i in range(batch_size):
            post_processed_ids.append(generated_ids[i, :generated_mask[i].sum()])
            
        return generated_ids, post_processed_ids
        
        
        
    def forward_svg_modal(self, input_ids, past_key_values):
        svg_embeddings = self.svg_embedding(input_ids)
        intermediate_states = self.model(
                past_key_values=past_key_values,
                inputs_embeds=svg_embeddings, 
                output_attentions=True, 
                output_hidden_states=True,
                use_cache=True,
            )
        
        hidden_states = intermediate_states.last_hidden_state
        svg_logits = self.svg_lm_head(hidden_states).float()
        svg_next_token_id = torch.argmax(svg_logits[:, -1, :], dim=-1).unsqueeze(1)
        
        return svg_next_token_id, intermediate_states.past_key_values
    
    @property
    def model_device(self):
        return next(self.parameters()).device
    
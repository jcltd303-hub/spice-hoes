"""Bounded social content preparation for disclosed fictional adult personas."""
import uuid

class ContentService:
 def __init__(self, personas, *, batch_cap=12):
  self.personas={p['id']:p for p in personas}; self.batch_cap=batch_cap
 def prepare(self, persona_id, pillars, count):
  p=self.personas.get(persona_id)
  if not p or p.get('fictional') is not True or p.get('age',0)<18: raise ValueError('Known fictional adult persona required')
  if not isinstance(pillars,list) or len(pillars)!=3 or any(not isinstance(x,str) or not x.strip() for x in pillars): raise ValueError('Exactly three content pillars required')
  if type(count) is not int or not 1<=count<=self.batch_cap: raise ValueError('Count exceeds configured batch cap')
  disclosure=p.get('disclosure','').strip()
  if not disclosure: raise ValueError('AI/fictional identity disclosure required')
  out=[]
  for i in range(count):
   pillar=pillars[i%3]
   out.append({'id':uuid.uuid4().hex,'persona_id':persona_id,'pillar':pillar,
    'hook':f'{pillar}: variant {(i//3)+1}','script':f'Original short-form concept about {pillar}.',
    'storyboard':['opening hook','persona beat','clear close'],
    'caption':f'{pillar} — {disclosure}','disclosure':disclosure,
    'status':'prepared','owner_review_required':True,'published':False})
  return out
 def approve(self,item,reviewer):
  if not item.get('disclosure') or not reviewer: raise ValueError('Disclosure and reviewer required')
  if item.get('reward_claim') and item.get('reward_eligibility_verified') is not True: raise ValueError('Unverified reward claim')
  return {**item,'status':'approved','reviewer':reviewer}

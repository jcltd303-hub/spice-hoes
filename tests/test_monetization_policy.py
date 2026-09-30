import unittest
from spicecore.monetization_policy import ProfitPolicy,Arm,arm_id

def arm(name):
    return Arm(name,"celeste","BR","pt-BR","mirror","offer-"+name,"affiliate")

class ProfitPolicyTests(unittest.TestCase):
    def test_reward_is_profit_first(self):
        p=ProfitPolicy()
        viral=[{"kind":"share","amount_cents":0} for _ in range(1000)]
        profitable=[{"kind":"sale","amount_cents":2000},{"kind":"production_cost","amount_cents":300}]
        self.assertGreater(p.reward(profitable),p.reward(viral))
        self.assertEqual(p.reward(profitable),1700)
        self.assertLessEqual(p.reward(viral),25)

    def test_refunds_and_risk_reduce_reward(self):
        p=ProfitPolicy()
        ev=[{"kind":"sale","amount_cents":2000},{"kind":"refund","amount_cents":500}]
        self.assertEqual(p.reward(ev,risk_cost_cents=250),1250)

    def test_untried_arm_gets_exploration(self):
        p=ProfitPolicy(exploration_rate=0,seed=1)
        a,b=arm("a"),arm("b")
        choice=p.choose([a,b],{"a":{"trials":10,"reward_cents":1000},"b":{"trials":0,"reward_cents":0}})
        # With exploration_rate zero this exploits positive evidence.
        self.assertEqual(choice["arm_id"],"a")
        q=ProfitPolicy(exploration_rate=.5,seed=1)
        self.assertEqual(q.choose([a,b],{"a":{"trials":10,"reward_cents":1000},"b":{"trials":0}})["arm_id"],"b")

    def test_budget_conserved(self):
        p=ProfitPolicy()
        out=p.allocate({"a":{"trials":10,"reward_cents":1000},"b":{"trials":2,"reward_cents":-50}},10000,floor_cents=500)
        self.assertEqual(sum(out.values()),10000)
        self.assertGreater(out["a"],out["b"])
        self.assertGreaterEqual(out["b"],500)

    def test_deeprl_fail_closed_until_mature_attribution(self):
        p=ProfitPolicy(min_deeprl_experiences=100)
        noisy=[{"reward_cents":10,"attributed":True,"mature":False} for _ in range(1000)]
        self.assertFalse(p.deeprl_status(noisy)["enabled"])
        mature=[{"reward_cents":10,"attributed":True,"mature":True} for _ in range(100)]
        self.assertTrue(p.deeprl_status(mature)["enabled"])

    def test_arm_id_stable(self):
        self.assertEqual(arm_id(format="mirror",geo="BR"),arm_id(geo="BR",format="mirror"))

if __name__=="__main__": unittest.main()

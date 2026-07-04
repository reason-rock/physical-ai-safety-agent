Feature: Physical AI Safety Agent public capstone demo

  Scenario: Forward fall policy improves but remains unsafe for unsupervised hardware
    Given a previous DARwIn-OP policy fell forward
    When the user asks Physical AI Safety Agent to run a stability-focused treatment
    And the control training rig keeps the previous stable baseline unchanged
    Then the Researcher PC evaluation compares both policies
    And the safety gate blocks unsupervised hardware testing
    And the report recommends supported low-speed testing only
